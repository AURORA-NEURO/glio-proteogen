"""Privacy-minimized append-only event ledger for M01-02 resolutions."""

from __future__ import annotations

# The chain scanner is intentionally exhaustive, append accepts a closed event material set,
# and DDL interpolation uses compile-time constants only. Typed failures carry stable context.
# ruff: noqa: PLR0913, TRY003
import sqlite3
from contextlib import contextmanager
from enum import StrEnum
from threading import RLock
from typing import TYPE_CHECKING, Any, Final, Self, cast

from pydantic import AwareDatetime, Field, TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_02.v1 import IdentityLineageResolution
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Identifier, Sha256Digest
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from types import TracebackType

GENESIS_DIGEST: Final[Sha256Digest] = "sha256:" + ("0" * 64)
MAX_EVENT_PAYLOAD_BYTES: Final = 8 * 1024 * 1024
EVENT_SCHEMA_VERSION: Final = "1.0.0"
_EVENT_TYPE_VALUE: Final = "resolution_committed"
_EVENT_ADAPTER: Final[TypeAdapter[IdentityLineageResolution]] = TypeAdapter(
    IdentityLineageResolution
)
_IDENTIFIER_ADAPTER: Final[TypeAdapter[Identifier]] = TypeAdapter(Identifier)
_DIGEST_ADAPTER: Final[TypeAdapter[Sha256Digest]] = TypeAdapter(Sha256Digest)
_TIME_ADAPTER: Final[TypeAdapter[AwareDatetime]] = TypeAdapter(AwareDatetime)
_FORBIDDEN_PERSISTED_KEYS: Final = frozenset(
    {
        "ancestry",
        "channels",
        "date_of_birth",
        "diagnosis",
        "direct_patient_id",
        "genotype",
        "identity_tokens",
        "kinase_state",
        "kinship",
        "medical_record_number",
        "mrn",
        "patient_name",
        "raw_allele_counts",
        "raw_reads",
        "recommended_treatment",
        "sex",
        "tag_digest",
        "token_digest",
        "treatment_recommendation",
    }
)
_TRIGGERS: Final = {
    "m0102_events_no_update": "m0102_events",
    "m0102_events_no_delete": "m0102_events",
    "m0102_resolutions_no_update": "m0102_resolutions",
    "m0102_resolutions_no_delete": "m0102_resolutions",
}
_EXPECTED_TRIGGER_SQL: Final = {
    "m0102_events_no_update": """
        CREATE TRIGGER m0102_events_no_update BEFORE UPDATE ON m0102_events
        BEGIN SELECT RAISE(ABORT, 'append-only table'); END
    """,
    "m0102_events_no_delete": """
        CREATE TRIGGER m0102_events_no_delete BEFORE DELETE ON m0102_events
        BEGIN SELECT RAISE(ABORT, 'append-only table'); END
    """,
    "m0102_resolutions_no_update": """
        CREATE TRIGGER m0102_resolutions_no_update BEFORE UPDATE ON m0102_resolutions
        BEGIN SELECT RAISE(ABORT, 'append-only table'); END
    """,
    "m0102_resolutions_no_delete": """
        CREATE TRIGGER m0102_resolutions_no_delete BEFORE DELETE ON m0102_resolutions
        BEGIN SELECT RAISE(ABORT, 'append-only table'); END
    """,
}
_EXPECTED_COLUMNS: Final = {
    "m0102_events": (
        ("seq", "INTEGER", 0, 1),
        ("event_type", "TEXT", 1, 0),
        ("request_id", "TEXT", 1, 0),
        ("request_digest", "TEXT", 1, 0),
        ("occurred_at", "TEXT", 1, 0),
        ("core_digest", "TEXT", 1, 0),
        ("resolution_digest", "TEXT", 1, 0),
        ("supersedes_resolution_digest", "TEXT", 0, 0),
        ("payload_json", "TEXT", 1, 0),
        ("payload_digest", "TEXT", 1, 0),
        ("previous_digest", "TEXT", 1, 0),
        ("event_digest", "TEXT", 1, 0),
    ),
    "m0102_resolutions": (
        ("resolution_digest", "TEXT", 0, 1),
        ("core_digest", "TEXT", 1, 0),
        ("event_seq", "INTEGER", 1, 0),
        ("supersedes_resolution_digest", "TEXT", 0, 0),
    ),
    "m0102_chain_state": (
        ("singleton", "INTEGER", 0, 1),
        ("event_count", "INTEGER", 1, 0),
        ("head_digest", "TEXT", 1, 0),
    ),
}
_EXPECTED_UNIQUE_INDEX_COLUMNS: Final = {
    "m0102_events": frozenset(
        {("request_id",), ("resolution_digest",), ("event_digest",)}
    ),
    "m0102_resolutions": frozenset(
        {
            ("event_seq",),
            ("supersedes_resolution_digest",),
            ("resolution_digest",),
        }
    ),
    "m0102_chain_state": frozenset(),
}
_EXPECTED_RESOLUTION_FOREIGN_KEYS: Final = (
    ("m0102_events", "event_seq", "seq", "NO ACTION", "NO ACTION"),
)
_DROP_DERIVED_OBJECT_SQL: Final = {
    ("m0102_resolutions", "table"): "DROP TABLE m0102_resolutions",
    ("m0102_resolutions", "view"): "DROP VIEW m0102_resolutions",
    ("m0102_chain_state", "table"): "DROP TABLE m0102_chain_state",
    ("m0102_chain_state", "view"): "DROP VIEW m0102_chain_state",
}


def _expected_table_sql() -> dict[str, str]:
    return {
        "m0102_events": f"""
            CREATE TABLE m0102_events (
                seq INTEGER PRIMARY KEY,
                event_type TEXT NOT NULL CHECK(event_type = '{_EVENT_TYPE_VALUE}'),
                request_id TEXT NOT NULL UNIQUE,
                request_digest TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                core_digest TEXT NOT NULL,
                resolution_digest TEXT NOT NULL UNIQUE,
                supersedes_resolution_digest TEXT,
                payload_json TEXT NOT NULL CHECK(
                    length(CAST(payload_json AS BLOB)) <= {MAX_EVENT_PAYLOAD_BYTES}
                ),
                payload_digest TEXT NOT NULL,
                previous_digest TEXT NOT NULL,
                event_digest TEXT NOT NULL UNIQUE
            )
        """,
        "m0102_resolutions": """
            CREATE TABLE m0102_resolutions (
                resolution_digest TEXT PRIMARY KEY,
                core_digest TEXT NOT NULL,
                event_seq INTEGER NOT NULL UNIQUE REFERENCES m0102_events(seq),
                supersedes_resolution_digest TEXT UNIQUE
            )
        """,
        "m0102_chain_state": """
            CREATE TABLE m0102_chain_state (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                event_count INTEGER NOT NULL CHECK(event_count >= 0),
                head_digest TEXT NOT NULL
            )
        """,
    }


def _normalized_sql(value: str) -> str:
    return " ".join(value.split())


class EventType(StrEnum):
    RESOLUTION_COMMITTED = _EVENT_TYPE_VALUE


class EventStoreError(RuntimeError):
    """Base error for the M01-02 append-only ledger."""


class IdempotencyConflictError(EventStoreError):
    """A request identifier was reused for different canonical content."""


class ResolutionNotFoundError(EventStoreError):
    """The requested immutable resolution does not exist."""


class ResolutionConflictError(EventStoreError):
    """A semantic resolution digest was reused by a different request."""


class ResolutionSupersessionConflictError(EventStoreError):
    """A correction points to an invalid or already superseded resolution."""


class ChainIntegrityError(EventStoreError):
    """Stored event history or its immutable projection failed verification."""


class PayloadTooLargeError(EventStoreError):
    """A persisted resolution envelope exceeded its explicit byte ceiling."""


class InvalidEventPayloadError(EventStoreError):
    """A persisted envelope is malformed, noncanonical, or privacy-unsafe."""


class EventRecord(FrozenModel):
    sequence: int = Field(ge=1)
    event_type: EventType
    request_id: Identifier
    request_digest: Sha256Digest
    occurred_at: AwareDatetime
    core_digest: Sha256Digest
    resolution_digest: Sha256Digest
    supersedes_resolution_digest: Sha256Digest | None
    payload_digest: Sha256Digest
    previous_digest: Sha256Digest
    event_digest: Sha256Digest
    payload: dict[str, Any]


class ChainVerification(FrozenModel):
    valid: bool
    event_count: int = Field(ge=0)
    head_digest: Sha256Digest
    reason: str | None = Field(default=None, max_length=512)


class M0102EventStore:
    """Append and verify immutable resolution events with exact-once replay."""

    def __init__(
        self,
        database_path: Path,
        *,
        trusted_event_count: int | None = None,
        trusted_head_digest: Sha256Digest | None = None,
        recovery_event_count: int | None = None,
        recovery_head_digest: Sha256Digest | None = None,
    ) -> None:
        recovery_anchor = _validated_anchor_pair(
            event_count=recovery_event_count,
            head_digest=recovery_head_digest,
            label="recovery",
        )
        if recovery_anchor is not None and (
            trusted_event_count is not None or trusted_head_digest is not None
        ):
            raise ValueError("recovery and prefix trust anchors cannot be combined")
        self._path = database_path.resolve()
        self._lock = RLock()
        self._closed = False
        self._connection = sqlite3.connect(
            self._path,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        try:
            self._configure()
            if recovery_anchor is not None:
                try:
                    self.recover_event_chain(
                        trusted_event_count=recovery_anchor[0],
                        trusted_head_digest=recovery_anchor[1],
                    )
                except BaseException:
                    self.close()
                    raise
                return
            self._create_schema()
            verification = self.verify_event_chain()
        except sqlite3.Error as error:
            self.close()
            raise ChainIntegrityError(
                "event ledger schema could not be initialized or verified"
            ) from error
        if not verification.valid:
            self.close()
            raise ChainIntegrityError(verification.reason or "event ledger is invalid")
        try:
            self._require_external_anchor(
                trusted_event_count=trusted_event_count,
                trusted_head_digest=trusted_head_digest,
                verification=verification,
            )
        except (ChainIntegrityError, ValidationError, ValueError):
            self.close()
            raise
        self._trusted_count = verification.event_count
        self._trusted_head = verification.head_digest
        self._data_version = self._read_data_version()

    def _require_external_anchor(
        self,
        *,
        trusted_event_count: int | None,
        trusted_head_digest: Sha256Digest | None,
        verification: ChainVerification,
    ) -> None:
        if (trusted_event_count is None) != (trusted_head_digest is None):
            raise ValueError("trusted event count and head digest must be supplied together")
        if trusted_event_count is None or trusted_head_digest is None:
            return
        if (
            isinstance(trusted_event_count, bool)
            or not isinstance(trusted_event_count, int)
            or trusted_event_count < 0
        ):
            raise ValueError("trusted event count must be a nonnegative integer")
        digest = _DIGEST_ADAPTER.validate_python(trusted_head_digest, strict=True)
        if trusted_event_count > verification.event_count:
            raise ChainIntegrityError("event history is shorter than its external trust anchor")
        if trusted_event_count == 0:
            if digest != GENESIS_DIGEST:
                raise ChainIntegrityError("external genesis anchor is invalid")
            return
        row = self._connection.execute(
            "SELECT event_digest FROM m0102_events WHERE seq = ?",
            (trusted_event_count,),
        ).fetchone()
        if row is None or cast("str", row["event_digest"]) != digest:
            raise ChainIntegrityError("event history does not match its external trust anchor")

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the SQLite connection; repeated calls are harmless."""

        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def find_replay(
        self,
        *,
        request_id: Identifier,
        request_digest: Sha256Digest,
    ) -> EventRecord | None:
        """Return an exact replay or reject request-ID reuse."""

        _IDENTIFIER_ADAPTER.validate_python(request_id, strict=True)
        _DIGEST_ADAPTER.validate_python(request_digest, strict=True)
        with self._lock:
            self._require_open()
            self._ensure_trusted()
            row = self._connection.execute(
                "SELECT * FROM m0102_events WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                return None
            if cast("str", row["request_digest"]) != request_digest:
                raise IdempotencyConflictError("request identifier was reused with new content")
            return self._record(row)

    def append_resolution(
        self,
        *,
        request_id: Identifier,
        request_digest: Sha256Digest,
        occurred_at: AwareDatetime,
        core_digest: Sha256Digest,
        resolution_digest: Sha256Digest,
        supersedes_resolution_digest: Sha256Digest | None,
        payload: dict[str, Any],
    ) -> EventRecord:
        """Atomically append one validated, privacy-safe resolution envelope."""

        _validate_storage_keys(
            request_id=request_id,
            request_digest=request_digest,
            occurred_at=occurred_at,
            core_digest=core_digest,
            resolution_digest=resolution_digest,
            supersedes_resolution_digest=supersedes_resolution_digest,
        )
        payload_bytes = canonical_json_bytes(payload)
        if len(payload_bytes) > MAX_EVENT_PAYLOAD_BYTES:
            raise PayloadTooLargeError("resolution event payload exceeds the byte limit")
        _reject_private_material(payload)
        payload_digest = sha256_digest(payload)

        with self._lock:
            self._require_open()
            with self._transaction():
                self._ensure_trusted()
                replay = self._find_replay_locked(request_id, request_digest)
                if replay is not None:
                    return replay
                collision = self._connection.execute(
                    "SELECT 1 FROM m0102_resolutions WHERE resolution_digest = ?",
                    (resolution_digest,),
                ).fetchone()
                if collision is not None:
                    raise ResolutionConflictError(
                        "resolution digest is already registered by another request"
                    )
                self._validate_supersession_locked(supersedes_resolution_digest)
                sequence = self._trusted_count + 1
                previous_digest = self._trusted_head
                event_digest = _event_digest(
                    sequence=sequence,
                    request_id=request_id,
                    request_digest=request_digest,
                    occurred_at=occurred_at,
                    core_digest=core_digest,
                    resolution_digest=resolution_digest,
                    supersedes_resolution_digest=supersedes_resolution_digest,
                    payload_digest=payload_digest,
                    previous_digest=previous_digest,
                )
                _validate_public_payload(
                    payload,
                    event_digest=event_digest,
                    expected_resolution_digest=resolution_digest,
                    expected_request_digest=request_digest,
                    expected_core_digest=core_digest,
                    expected_supersedes_resolution_digest=supersedes_resolution_digest,
                )
                occurred_text = _canonical_time(occurred_at)
                try:
                    self._connection.execute(
                        """
                        INSERT INTO m0102_events (
                            seq, event_type, request_id, request_digest, occurred_at,
                            core_digest, resolution_digest, supersedes_resolution_digest,
                            payload_json, payload_digest, previous_digest, event_digest
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sequence,
                            EventType.RESOLUTION_COMMITTED.value,
                            request_id,
                            request_digest,
                            occurred_text,
                            core_digest,
                            resolution_digest,
                            supersedes_resolution_digest,
                            payload_bytes.decode("utf-8"),
                            payload_digest,
                            previous_digest,
                            event_digest,
                        ),
                    )
                    self._connection.execute(
                        """
                        INSERT INTO m0102_resolutions (
                            resolution_digest, core_digest, event_seq,
                            supersedes_resolution_digest
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            resolution_digest,
                            core_digest,
                            sequence,
                            supersedes_resolution_digest,
                        ),
                    )
                    self._connection.execute(
                        """
                        UPDATE m0102_chain_state
                        SET event_count = ?, head_digest = ?
                        WHERE singleton = 1
                        """,
                        (sequence, event_digest),
                    )
                except sqlite3.Error as error:
                    raise EventStoreError("resolution event could not be appended") from error
                self._trusted_count = sequence
                self._trusted_head = event_digest
                row = self._connection.execute(
                    "SELECT * FROM m0102_events WHERE seq = ?",
                    (sequence,),
                ).fetchone()
                if row is None:
                    raise ChainIntegrityError("new resolution event is not readable")
                record = self._record(row)
            self._data_version = self._read_data_version()
        return record

    def get_resolution(self, resolution_digest: Sha256Digest) -> EventRecord:
        """Retrieve one immutable resolution event by its semantic digest."""

        _DIGEST_ADAPTER.validate_python(resolution_digest, strict=True)
        with self._lock:
            self._require_open()
            self._ensure_trusted()
            row = self._connection.execute(
                "SELECT e.* FROM m0102_events e JOIN m0102_resolutions r ON r.event_seq=e.seq "
                "WHERE r.resolution_digest = ?",
                (resolution_digest,),
            ).fetchone()
            if row is None:
                raise ResolutionNotFoundError("identity resolution is not registered")
            return self._record(row)

    def verify_event_chain(self) -> ChainVerification:
        """Exhaustively verify schema controls, chain links, payloads, and projection."""

        with self._lock:
            if self._closed:
                raise EventStoreError("event store is closed")
            try:
                rollback_failure = self._trusted_prefix_failure_locked()
                if rollback_failure is not None:
                    return _invalid(
                        rollback_failure,
                        getattr(self, "_trusted_count", 0),
                        getattr(self, "_trusted_head", GENESIS_DIGEST),
                    )
                return self._verify_locked()
            except (sqlite3.Error, InvalidEventPayloadError, ValidationError, ValueError) as error:
                return ChainVerification(
                    valid=False,
                    event_count=0,
                    head_digest=GENESIS_DIGEST,
                    reason=f"event ledger verification failed: {type(error).__name__}",
                )

    def recover_event_chain(
        self,
        *,
        trusted_event_count: int,
        trusted_head_digest: Sha256Digest,
    ) -> ChainVerification:
        """Rebuild derived ledger state from an exactly anchored immutable history.

        The caller must obtain both anchor values independently of this database.  Recovery
        scans and authenticates every event without consulting the projection or checkpoint,
        refuses any event mutation or truncation beneath a live trusted prefix, and changes
        only the derived projection, checkpoint, and their append-only trigger controls.
        """

        anchor = _validated_required_anchor(
            event_count=trusted_event_count,
            head_digest=trusted_head_digest,
            label="recovery",
        )
        with self._lock:
            self._require_open()
            try:
                with self._transaction():
                    verification = self._recover_from_anchor_locked(anchor)
            except ChainIntegrityError:
                raise
            except (
                InvalidEventPayloadError,
                ValidationError,
                ValueError,
                sqlite3.Error,
            ) as error:
                raise ChainIntegrityError("immutable event history is not recoverable") from error
            self._trusted_count = verification.event_count
            self._trusted_head = verification.head_digest
            self._data_version = self._read_data_version()
            return verification

    def _recover_from_anchor_locked(
        self,
        anchor: tuple[int, Sha256Digest],
    ) -> ChainVerification:
        prefix_failure = self._trusted_prefix_failure_locked()
        if prefix_failure is not None:
            raise ChainIntegrityError(prefix_failure)
        self._require_recovery_not_behind_live_prefix(*anchor)
        chain = self._scan_immutable_events_locked()
        if not chain.valid:
            raise ChainIntegrityError(
                chain.reason or "immutable event history is not recoverable"
            )
        if (chain.event_count, chain.head_digest) != anchor:
            raise ChainIntegrityError(
                "trusted recovery anchor does not exactly match event history"
            )
        self._rebuild_derived_state_locked(chain)
        verification = self._verify_locked()
        if not verification.valid:
            raise ChainIntegrityError(
                verification.reason or "recovery postcondition verification failed"
            )
        return verification

    def _configure(self) -> None:
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.execute("PRAGMA trusted_schema = OFF")

    def _create_schema(self) -> None:
        for table_sql in _expected_table_sql().values():
            statement = table_sql.replace(
                "CREATE TABLE",
                "CREATE TABLE IF NOT EXISTS",
                1,
            )
            self._connection.execute(statement)
        self._connection.execute(
            "INSERT OR IGNORE INTO m0102_chain_state(singleton,event_count,head_digest) "
            "VALUES (1,0,?)",
            (GENESIS_DIGEST,),
        )
        for trigger_name, trigger_sql in _EXPECTED_TRIGGER_SQL.items():
            self._connection.execute(
                trigger_sql.replace(
                    f"CREATE TRIGGER {trigger_name}",
                    f"CREATE TRIGGER IF NOT EXISTS {trigger_name}",
                    1,
                )
            )

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise
        else:
            self._connection.execute("COMMIT")

    def _require_open(self) -> None:
        if self._closed:
            raise EventStoreError("event store is closed")

    def _read_data_version(self) -> int:
        row = self._connection.execute("PRAGMA data_version").fetchone()
        if row is None:
            raise EventStoreError("SQLite data version is unavailable")
        return cast("int", row[0])

    def _ensure_trusted(self) -> None:
        data_version = self._read_data_version()
        row = self._connection.execute(
            "SELECT event_count,head_digest FROM m0102_chain_state WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise ChainIntegrityError("event chain checkpoint is missing")
        current = (cast("int", row["event_count"]), cast("str", row["head_digest"]))
        if data_version != self._data_version or current != (
            self._trusted_count,
            self._trusted_head,
        ):
            rollback_failure = self._trusted_prefix_failure_locked()
            if rollback_failure is not None:
                raise ChainIntegrityError(rollback_failure)
            verification = self._verify_locked()
            if not verification.valid:
                raise ChainIntegrityError(verification.reason or "event ledger is invalid")
            self._trusted_count = verification.event_count
            self._trusted_head = verification.head_digest
            self._data_version = data_version

    def _trusted_prefix_failure_locked(self) -> str | None:
        if not hasattr(self, "_trusted_count") or self._trusted_count == 0:
            return None
        row = self._connection.execute(
            "SELECT event_digest FROM m0102_events WHERE seq = ?",
            (self._trusted_count,),
        ).fetchone()
        if row is None:
            return "event history was truncated below the trusted checkpoint"
        if cast("str", row["event_digest"]) != self._trusted_head:
            return "event history was rewritten at the trusted checkpoint"
        return None

    def _require_recovery_not_behind_live_prefix(
        self,
        event_count: int,
        head_digest: Sha256Digest,
    ) -> None:
        if not hasattr(self, "_trusted_count"):
            return
        if event_count < self._trusted_count:
            raise ChainIntegrityError("recovery anchor is behind the live trusted prefix")
        if event_count == self._trusted_count and head_digest != self._trusted_head:
            raise ChainIntegrityError("recovery anchor rewrites the live trusted prefix")

    def _rebuild_derived_state_locked(self, chain: ChainVerification) -> None:
        trigger_rows = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name IN ('m0102_events','m0102_resolutions')"
        ).fetchall()
        for row in trigger_rows:
            trigger_name = cast("str", row["name"]).replace('"', '""')
            self._connection.execute(f'DROP TRIGGER "{trigger_name}"')

        self._drop_derived_object_locked("m0102_resolutions")
        self._drop_derived_object_locked("m0102_chain_state")
        self._connection.execute(_expected_table_sql()["m0102_resolutions"])
        self._connection.execute(_expected_table_sql()["m0102_chain_state"])
        rows = self._connection.execute(
            "SELECT resolution_digest,core_digest,seq,supersedes_resolution_digest "
            "FROM m0102_events ORDER BY seq"
        ).fetchall()
        self._connection.executemany(
            "INSERT INTO m0102_resolutions ("
            "resolution_digest,core_digest,event_seq,supersedes_resolution_digest"
            ") VALUES (?,?,?,?)",
            (
                (
                    row["resolution_digest"],
                    row["core_digest"],
                    row["seq"],
                    row["supersedes_resolution_digest"],
                )
                for row in rows
            ),
        )
        self._connection.execute(
            "INSERT INTO m0102_chain_state(singleton,event_count,head_digest) "
            "VALUES (1,?,?)",
            (chain.event_count, chain.head_digest),
        )
        for trigger_sql in _EXPECTED_TRIGGER_SQL.values():
            self._connection.execute(trigger_sql)

    def _drop_derived_object_locked(self, object_name: str) -> None:
        row = self._connection.execute(
            "SELECT type FROM sqlite_master WHERE name = ?",
            (object_name,),
        ).fetchone()
        if row is None:
            return
        statement = _DROP_DERIVED_OBJECT_SQL.get(
            (object_name, cast("str", row["type"])),
        )
        if statement is None:
            raise ChainIntegrityError("derived ledger name has an unsupported object type")
        self._connection.execute(statement)

    def _find_replay_locked(
        self,
        request_id: Identifier,
        request_digest: Sha256Digest,
    ) -> EventRecord | None:
        row = self._connection.execute(
            "SELECT * FROM m0102_events WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if row is None:
            return None
        if cast("str", row["request_digest"]) != request_digest:
            raise IdempotencyConflictError("request identifier was reused with new content")
        return self._record(row)

    def _validate_supersession_locked(self, predecessor: Sha256Digest | None) -> None:
        if predecessor is None:
            return
        exists = self._connection.execute(
            "SELECT 1 FROM m0102_resolutions WHERE resolution_digest = ?",
            (predecessor,),
        ).fetchone()
        if exists is None:
            raise ResolutionSupersessionConflictError("superseded resolution does not exist")
        successor = self._connection.execute(
            "SELECT 1 FROM m0102_resolutions WHERE supersedes_resolution_digest = ?",
            (predecessor,),
        ).fetchone()
        if successor is not None:
            raise ResolutionSupersessionConflictError("resolution already has a successor")

    def _verify_locked(self) -> ChainVerification:  # noqa: PLR0911
        storage_failure = self._verify_storage_schema_locked()
        if storage_failure is not None:
            return _invalid(storage_failure)
        trigger_failure = self._verify_append_only_controls_locked()
        if trigger_failure is not None:
            return _invalid(trigger_failure)
        chain = self._scan_immutable_events_locked(verify_event_schema=False)
        if not chain.valid:
            return chain
        rows = self._connection.execute("SELECT * FROM m0102_events ORDER BY seq").fetchall()
        checkpoint = self._connection.execute(
            "SELECT event_count,head_digest FROM m0102_chain_state WHERE singleton=1"
        ).fetchone()
        if checkpoint is None or (
            cast("int", checkpoint["event_count"]), cast("str", checkpoint["head_digest"])
        ) != (chain.event_count, chain.head_digest):
            return _invalid(
                "event checkpoint does not match history",
                chain.event_count,
                chain.head_digest,
            )
        projections = self._connection.execute(
            "SELECT * FROM m0102_resolutions ORDER BY event_seq"
        ).fetchall()
        if len(projections) != len(rows):
            return _invalid(
                "resolution projection count does not match history",
                chain.event_count,
                chain.head_digest,
            )
        for projection, event in zip(projections, rows, strict=True):
            if (
                cast("str", projection["resolution_digest"])
                != cast("str", event["resolution_digest"])
                or cast("str", projection["core_digest"]) != cast("str", event["core_digest"])
                or cast("int", projection["event_seq"]) != cast("int", event["seq"])
                or cast("str | None", projection["supersedes_resolution_digest"])
                != cast("str | None", event["supersedes_resolution_digest"])
            ):
                return _invalid(
                    "resolution projection does not match history",
                    chain.event_count,
                    chain.head_digest,
                )
        return chain

    def _scan_immutable_events_locked(  # noqa: C901, PLR0911
        self,
        *,
        verify_event_schema: bool = True,
    ) -> ChainVerification:
        if verify_event_schema:
            storage_failure = self._verify_storage_schema_locked(event_table_only=True)
            if storage_failure is not None:
                return _invalid(storage_failure)
        rows = self._connection.execute("SELECT * FROM m0102_events ORDER BY seq").fetchall()
        previous = GENESIS_DIGEST
        seen_requests: set[str] = set()
        seen_resolutions: set[str] = set()
        predecessor_children: set[str] = set()
        for expected_sequence, row in enumerate(rows, start=1):
            sequence = cast("int", row["seq"])
            if sequence != expected_sequence:
                return _invalid("event sequences are not contiguous", len(rows), previous)
            if cast("str", row["event_type"]) != _EVENT_TYPE_VALUE:
                return _invalid("event type is invalid", len(rows), previous)
            request_id = cast("str", row["request_id"])
            resolution_digest = cast("str", row["resolution_digest"])
            if request_id in seen_requests or resolution_digest in seen_resolutions:
                return _invalid("event identity is duplicated", len(rows), previous)
            seen_requests.add(request_id)
            seen_resolutions.add(resolution_digest)
            if cast("str", row["previous_digest"]) != previous:
                return _invalid("event chain predecessor does not match", len(rows), previous)
            payload = _decode_payload(cast("str", row["payload_json"]))
            payload_digest = sha256_digest(payload)
            if payload_digest != cast("str", row["payload_digest"]):
                return _invalid("event payload digest does not match", len(rows), previous)
            predecessor = cast("str | None", row["supersedes_resolution_digest"])
            if predecessor is not None:
                if predecessor not in seen_resolutions or predecessor in predecessor_children:
                    return _invalid("resolution supersession chain is invalid", len(rows), previous)
                predecessor_children.add(predecessor)
            occurred_at = _TIME_ADAPTER.validate_python(
                cast("str", row["occurred_at"]),
                strict=False,
            )
            if _canonical_time(occurred_at) != cast("str", row["occurred_at"]):
                return _invalid("event occurrence time is not canonical", len(rows), previous)
            expected_digest = _event_digest(
                sequence=sequence,
                request_id=_IDENTIFIER_ADAPTER.validate_python(request_id, strict=True),
                request_digest=_DIGEST_ADAPTER.validate_python(
                    cast("str", row["request_digest"]), strict=True
                ),
                occurred_at=occurred_at,
                core_digest=_DIGEST_ADAPTER.validate_python(
                    cast("str", row["core_digest"]), strict=True
                ),
                resolution_digest=_DIGEST_ADAPTER.validate_python(resolution_digest, strict=True),
                supersedes_resolution_digest=(
                    _DIGEST_ADAPTER.validate_python(predecessor, strict=True)
                    if predecessor is not None
                    else None
                ),
                payload_digest=payload_digest,
                previous_digest=previous,
            )
            actual_digest = cast("str", row["event_digest"])
            if actual_digest != expected_digest:
                return _invalid("event digest does not match", len(rows), previous)
            _validate_public_payload(
                payload,
                event_digest=expected_digest,
                expected_resolution_digest=resolution_digest,
                expected_request_digest=cast("str", row["request_digest"]),
                expected_core_digest=cast("str", row["core_digest"]),
                expected_supersedes_resolution_digest=predecessor,
            )
            previous = expected_digest
        return ChainVerification(
            valid=True,
            event_count=len(rows),
            head_digest=previous,
        )

    def _verify_storage_schema_locked(  # noqa: C901, PLR0911
        self,
        *,
        event_table_only: bool = False,
    ) -> str | None:
        table_names = (
            ("m0102_events",)
            if event_table_only
            else tuple(_EXPECTED_COLUMNS)
        )
        if event_table_only:
            rows = self._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='table' "
                "AND name = 'm0102_events'"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='table' "
                "AND name IN ('m0102_events','m0102_resolutions','m0102_chain_state')"
            ).fetchall()
        actual_sql = {
            row["name"]: _normalized_sql(row["sql"])
            for row in rows
            if isinstance(row["name"], str) and isinstance(row["sql"], str)
        }
        expected_sql = {
            name: _normalized_sql(_expected_table_sql()[name]) for name in table_names
        }
        if actual_sql != expected_sql:
            return "ledger table definitions or constraints are missing or altered"
        for table in table_names:
            expected_columns = _EXPECTED_COLUMNS[table]
            columns = self._connection.execute(
                'SELECT name,type,"notnull" AS is_not_null,pk '
                "FROM pragma_table_info(?) ORDER BY cid",
                (table,),
            ).fetchall()
            actual_columns = tuple(
                (
                    cast("str", column["name"]),
                    cast("str", column["type"]).upper(),
                    cast("int", column["is_not_null"]),
                    cast("int", column["pk"]),
                )
                for column in columns
            )
            if actual_columns != expected_columns:
                return f"ledger column contract is altered for {table}"
            indexes = self._connection.execute(
                'SELECT name,"unique" AS is_unique FROM pragma_index_list(?)',
                (table,),
            ).fetchall()
            unique_columns: set[tuple[str, ...]] = set()
            for index in indexes:
                if cast("int", index["is_unique"]) != 1:
                    continue
                indexed = self._connection.execute(
                    "SELECT name FROM pragma_index_info(?) ORDER BY seqno",
                    (index["name"],),
                ).fetchall()
                unique_columns.add(tuple(cast("str", item["name"]) for item in indexed))
            if frozenset(unique_columns) != _EXPECTED_UNIQUE_INDEX_COLUMNS[table]:
                return f"ledger uniqueness contract is altered for {table}"
        if event_table_only:
            return None
        foreign_keys = self._connection.execute(
            'SELECT "table","from","to",on_update,on_delete '
            "FROM pragma_foreign_key_list('m0102_resolutions') ORDER BY id,seq"
        ).fetchall()
        actual_foreign_keys = tuple(
            (
                cast("str", row["table"]),
                cast("str", row["from"]),
                cast("str", row["to"]),
                cast("str", row["on_update"]),
                cast("str", row["on_delete"]),
            )
            for row in foreign_keys
        )
        if actual_foreign_keys != _EXPECTED_RESOLUTION_FOREIGN_KEYS:
            return "ledger foreign-key contract is altered"
        if self._connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            return "ledger foreign-key integrity check failed"
        return None

    def _verify_append_only_controls_locked(self) -> str | None:
        rows = self._connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name IN ('m0102_events','m0102_resolutions')"
        ).fetchall()
        actual = {
            cast("str", row["name"]): _normalized_sql(cast("str", row["sql"]))
            for row in rows
        }
        expected = {
            name: _normalized_sql(sql) for name, sql in _EXPECTED_TRIGGER_SQL.items()
        }
        if actual != expected:
            return "append-only database controls are missing or altered"
        return None

    def _record(self, row: sqlite3.Row) -> EventRecord:
        payload = _decode_payload(cast("str", row["payload_json"]))
        event_digest = _DIGEST_ADAPTER.validate_python(
            cast("str", row["event_digest"]),
            strict=True,
        )
        _validate_public_payload(
            payload,
            event_digest=event_digest,
            expected_resolution_digest=cast("str", row["resolution_digest"]),
            expected_request_digest=cast("str", row["request_digest"]),
            expected_core_digest=cast("str", row["core_digest"]),
            expected_supersedes_resolution_digest=cast(
                "str | None",
                row["supersedes_resolution_digest"],
            ),
        )
        return EventRecord(
            sequence=cast("int", row["seq"]),
            event_type=EventType(cast("str", row["event_type"])),
            request_id=_IDENTIFIER_ADAPTER.validate_python(
                cast("str", row["request_id"]), strict=True
            ),
            request_digest=_DIGEST_ADAPTER.validate_python(
                cast("str", row["request_digest"]), strict=True
            ),
            occurred_at=_TIME_ADAPTER.validate_python(
                cast("str", row["occurred_at"]), strict=False
            ),
            core_digest=_DIGEST_ADAPTER.validate_python(
                cast("str", row["core_digest"]), strict=True
            ),
            resolution_digest=_DIGEST_ADAPTER.validate_python(
                cast("str", row["resolution_digest"]), strict=True
            ),
            supersedes_resolution_digest=(
                _DIGEST_ADAPTER.validate_python(
                    cast("str", row["supersedes_resolution_digest"]), strict=True
                )
                if row["supersedes_resolution_digest"] is not None
                else None
            ),
            payload_digest=_DIGEST_ADAPTER.validate_python(
                cast("str", row["payload_digest"]), strict=True
            ),
            previous_digest=_DIGEST_ADAPTER.validate_python(
                cast("str", row["previous_digest"]), strict=True
            ),
            event_digest=event_digest,
            payload=payload,
        )


def _validated_anchor_pair(
    *,
    event_count: int | None,
    head_digest: Sha256Digest | None,
    label: str,
) -> tuple[int, Sha256Digest] | None:
    if (event_count is None) != (head_digest is None):
        raise ValueError(f"{label} event count and head digest must be supplied together")
    if event_count is None or head_digest is None:
        return None
    return _validated_required_anchor(
        event_count=event_count,
        head_digest=head_digest,
        label=label,
    )


def _validated_required_anchor(
    *,
    event_count: int,
    head_digest: Sha256Digest,
    label: str,
) -> tuple[int, Sha256Digest]:
    if isinstance(event_count, bool) or not isinstance(event_count, int) or event_count < 0:
        raise ValueError(f"{label} event count must be a nonnegative integer")
    try:
        digest = _DIGEST_ADAPTER.validate_python(head_digest, strict=True)
    except ValidationError:
        raise ValueError(f"{label} head digest must be a namespaced SHA-256 digest") from None
    return event_count, digest


def _canonical_time(value: AwareDatetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _validate_storage_keys(
    *,
    request_id: Identifier,
    request_digest: Sha256Digest,
    occurred_at: AwareDatetime,
    core_digest: Sha256Digest,
    resolution_digest: Sha256Digest,
    supersedes_resolution_digest: Sha256Digest | None,
) -> None:
    _IDENTIFIER_ADAPTER.validate_python(request_id, strict=True)
    for digest in (request_digest, core_digest, resolution_digest):
        _DIGEST_ADAPTER.validate_python(digest, strict=True)
    if supersedes_resolution_digest is not None:
        _DIGEST_ADAPTER.validate_python(supersedes_resolution_digest, strict=True)
    _TIME_ADAPTER.validate_python(occurred_at, strict=True)


def _event_digest(
    *,
    sequence: int,
    request_id: Identifier,
    request_digest: Sha256Digest,
    occurred_at: AwareDatetime,
    core_digest: Sha256Digest,
    resolution_digest: Sha256Digest,
    supersedes_resolution_digest: Sha256Digest | None,
    payload_digest: Sha256Digest,
    previous_digest: Sha256Digest,
) -> Sha256Digest:
    return sha256_digest(
        {
            "event_schema_version": EVENT_SCHEMA_VERSION,
            "event_type": EventType.RESOLUTION_COMMITTED.value,
            "sequence": sequence,
            "request_id": request_id,
            "request_digest": request_digest,
            "occurred_at": occurred_at,
            "core_digest": core_digest,
            "resolution_digest": resolution_digest,
            "supersedes_resolution_digest": supersedes_resolution_digest,
            "payload_digest": payload_digest,
            "previous_digest": previous_digest,
        }
    )


def _decode_payload(payload_json: str) -> dict[str, Any]:
    try:
        decoded = strict_json_loads(payload_json, max_bytes=MAX_EVENT_PAYLOAD_BYTES)
    except StrictJsonError:
        raise InvalidEventPayloadError("resolution event payload is invalid") from None
    if not isinstance(decoded, dict):
        raise InvalidEventPayloadError("resolution event payload must be an object")
    if canonical_json_bytes(decoded).decode("utf-8") != payload_json:
        raise InvalidEventPayloadError("resolution event payload is not canonical JSON")
    _reject_private_material(decoded)
    return cast("dict[str, Any]", decoded)


def _validate_public_payload(
    payload: dict[str, Any],
    *,
    event_digest: Sha256Digest,
    expected_resolution_digest: str,
    expected_request_digest: str,
    expected_core_digest: str,
    expected_supersedes_resolution_digest: str | None,
) -> IdentityLineageResolution:
    if "event_digest" in payload:
        raise InvalidEventPayloadError("stored payload must not embed its ledger event digest")
    candidate = {**payload, "event_digest": event_digest}
    try:
        validated = _EVENT_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
    except ValidationError as error:
        raise InvalidEventPayloadError("stored resolution payload violates its contract") from error
    if validated.resolution_digest != expected_resolution_digest:
        raise InvalidEventPayloadError("stored resolution identity does not match its event")
    if validated.request_digest != expected_request_digest:
        raise InvalidEventPayloadError("stored request identity does not match its event")
    if validated.core_digest != expected_core_digest:
        raise InvalidEventPayloadError("stored semantic core does not match its event")
    if validated.supersedes_resolution_digest != expected_supersedes_resolution_digest:
        raise InvalidEventPayloadError("stored supersession does not match its event")
    return validated


def _reject_private_material(value: object) -> None:
    if isinstance(value, dict):
        forbidden = set(value) & _FORBIDDEN_PERSISTED_KEYS
        if forbidden:
            raise InvalidEventPayloadError("resolution payload contains private input material")
        for item in value.values():
            _reject_private_material(item)
    elif isinstance(value, list):
        for item in value:
            _reject_private_material(item)


def _invalid(
    reason: str,
    event_count: int = 0,
    head_digest: Sha256Digest = GENESIS_DIGEST,
) -> ChainVerification:
    return ChainVerification(
        valid=False,
        event_count=event_count,
        head_digest=head_digest,
        reason=reason,
    )


__all__ = [
    "GENESIS_DIGEST",
    "MAX_EVENT_PAYLOAD_BYTES",
    "ChainIntegrityError",
    "ChainVerification",
    "EventRecord",
    "EventStoreError",
    "EventType",
    "IdempotencyConflictError",
    "InvalidEventPayloadError",
    "M0102EventStore",
    "PayloadTooLargeError",
    "ResolutionConflictError",
    "ResolutionNotFoundError",
    "ResolutionSupersessionConflictError",
]

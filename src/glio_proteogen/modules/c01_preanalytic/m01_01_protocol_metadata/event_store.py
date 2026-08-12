"""Append-only SQLite persistence for M01-01.

The event log is the source of truth.  The protocol table is an immutable projection that
can be rebuilt from registration events after a verified recovery.  Event payloads are
canonical JSON and conformance events intentionally contain no submitted metadata values.
"""

from __future__ import annotations

# Domain-specific failures carry contextual messages, and the deliberately exhaustive chain
# scanner benefits from direct fail-fast branches.  The DDL interpolation is restricted to a
# validated integer ceiling and a compile-time digest, never caller-controlled SQL.
# Sha256Digest must remain a runtime import because FastAPI/Pydantic resolves the public
# ChainVerification annotation.  The exhaustive scanner is intentionally branch-heavy.
# ruff: noqa: C901, PLR0911, PLR0912, PLR0913, S608, TRY003
import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, Self, cast

from glio_proteogen.contracts.m01_01.canonical import (
    canonical_protocol_bytes,
    normalized_protocol,
    protocol_digest,
)
from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceProfile,
    ProtocolReference,
    ProtocolSchema,
    ProtocolSchemaReceipt,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.kernel.strict_json import strict_json_loads

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path
    from types import TracebackType

GENESIS_DIGEST: Final[Sha256Digest] = f"sha256:{'0' * 64}"
EVENT_SCHEMA_VERSION: Final = "1.0.0"
DEFAULT_MAX_PAYLOAD_BYTES: Final = 2 * 1024 * 1024
_DIGEST_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_PATTERN: Final = re.compile(r"^[a-zA-Z][a-zA-Z0-9._:-]{0,127}$")
_REGISTRATION_PAYLOAD_KEYS: Final = frozenset(
    {
        "event_schema_version",
        "output_type",
        "receipt_version",
        "protocol",
        "protocol_schema",
        "support",
        "uncertainty",
        "provenance",
        "evidence",
        "limitations",
    }
)
_EVALUATION_PAYLOAD_KEYS: Final = frozenset(
    {
        "event_schema_version",
        "output_type",
        "profile_version",
        "protocol",
        "document_digest",
        "decision",
        "support",
        "issues",
        "uncertainty",
        "provenance",
        "evidence",
        "limitations",
        "human_review_required",
        "evaluated_at",
    }
)
_EXPECTED_TRIGGER_SQL: Final = {
    "m0101_events_no_update": """
        CREATE TRIGGER m0101_events_no_update
        BEFORE UPDATE ON m0101_events
        BEGIN
            SELECT RAISE(ABORT, 'M01-01 events are append-only');
        END
    """,
    "m0101_events_no_delete": """
        CREATE TRIGGER m0101_events_no_delete
        BEFORE DELETE ON m0101_events
        BEGIN
            SELECT RAISE(ABORT, 'M01-01 events are append-only');
        END
    """,
    "m0101_protocols_no_update": """
        CREATE TRIGGER m0101_protocols_no_update
        BEFORE UPDATE ON m0101_protocols
        BEGIN
            SELECT RAISE(ABORT, 'M01-01 protocols are immutable');
        END
    """,
    "m0101_protocols_no_delete": """
        CREATE TRIGGER m0101_protocols_no_delete
        BEFORE DELETE ON m0101_protocols
        BEGIN
            SELECT RAISE(ABORT, 'M01-01 protocols are immutable');
        END
    """,
}
_EXPECTED_COLUMNS: Final = {
    "m0101_events": (
        ("sequence", "INTEGER", 0, 1),
        ("event_type", "TEXT", 1, 0),
        ("request_id", "TEXT", 1, 0),
        ("request_digest", "TEXT", 1, 0),
        ("occurred_at", "TEXT", 1, 0),
        ("previous_digest", "TEXT", 1, 0),
        ("event_digest", "TEXT", 1, 0),
        ("payload_json", "TEXT", 1, 0),
    ),
    "m0101_protocols": (
        ("schema_id", "TEXT", 1, 1),
        ("version", "TEXT", 1, 2),
        ("protocol_digest", "TEXT", 1, 0),
        ("schema_json", "TEXT", 1, 0),
        ("registration_event_digest", "TEXT", 1, 0),
    ),
    "m0101_chain_state": (
        ("singleton", "INTEGER", 0, 1),
        ("head_sequence", "INTEGER", 1, 0),
        ("head_digest", "TEXT", 1, 0),
        ("event_count", "INTEGER", 1, 0),
    ),
}
_EXPECTED_UNIQUE_INDEX_COLUMNS: Final = {
    "m0101_events": frozenset({("request_id",), ("event_digest",)}),
    "m0101_protocols": frozenset(
        {
            ("schema_id", "version"),
            ("protocol_digest",),
            ("registration_event_digest",),
        }
    ),
    "m0101_chain_state": frozenset(),
}
_EXPECTED_PROTOCOL_FOREIGN_KEYS: Final = (
    (
        "m0101_events",
        "registration_event_digest",
        "event_digest",
        "NO ACTION",
        "NO ACTION",
    ),
)


def _expected_table_sql(max_chars: int) -> dict[str, str]:
    return {
        "m0101_events": f"""
            CREATE TABLE m0101_events (
                sequence INTEGER PRIMARY KEY,
                event_type TEXT NOT NULL CHECK (
                    event_type IN ('protocol_registered', 'metadata_evaluated')
                ),
                request_id TEXT NOT NULL UNIQUE,
                request_digest TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                previous_digest TEXT NOT NULL,
                event_digest TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL CHECK (length(payload_json) <= {max_chars})
            )
        """,
        "m0101_protocols": f"""
            CREATE TABLE m0101_protocols (
                schema_id TEXT NOT NULL,
                version TEXT NOT NULL,
                protocol_digest TEXT NOT NULL UNIQUE,
                schema_json TEXT NOT NULL CHECK (length(schema_json) <= {max_chars}),
                registration_event_digest TEXT NOT NULL UNIQUE,
                PRIMARY KEY (schema_id, version),
                FOREIGN KEY (registration_event_digest)
                    REFERENCES m0101_events(event_digest)
            )
        """,
        "m0101_chain_state": """
            CREATE TABLE m0101_chain_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                head_sequence INTEGER NOT NULL CHECK (head_sequence >= 0),
                head_digest TEXT NOT NULL,
                event_count INTEGER NOT NULL CHECK (event_count >= 0)
            )
        """,
    }


def _normalized_sql(value: str) -> str:
    # Preserve quoted-literal case: unlike SQL keywords, CHECK/trigger string values are
    # case-sensitive and therefore part of the attested constraint semantics.
    return " ".join(value.split())


class EventType(StrEnum):
    """Closed event vocabulary owned by M01-01."""

    PROTOCOL_REGISTERED = "protocol_registered"
    METADATA_EVALUATED = "metadata_evaluated"


class EventStoreError(RuntimeError):
    """Base class for deterministic persistence failures."""


class IdempotencyConflictError(EventStoreError):
    """A request identifier was reused for different canonical input."""


class ProtocolVersionConflictError(EventStoreError):
    """An immutable schema identifier/version was reused for different content."""


class ProtocolNotFoundError(EventStoreError):
    """The requested immutable protocol does not exist."""


class ChainIntegrityError(EventStoreError):
    """The persisted event chain or immutable projection failed verification."""


class PayloadTooLargeError(EventStoreError):
    """A canonical event or protocol payload exceeded its configured storage ceiling."""


class InvalidEventPayloadError(EventStoreError):
    """An event payload violated its closed, privacy-preserving schema."""


@dataclass(frozen=True, slots=True)
class EventRecord:
    """One verified event, with its decoded canonical payload."""

    sequence: int
    event_type: EventType
    request_id: str
    request_digest: Sha256Digest
    occurred_at: str
    previous_digest: Sha256Digest
    event_digest: Sha256Digest
    payload: Mapping[str, Any]
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class StoredProtocol:
    """An immutable protocol projection and its first registration event."""

    reference: ProtocolReference
    schema: ProtocolSchema
    registration_event: EventRecord


class ChainVerification(FrozenModel):
    """Result of a complete event-chain and registry-projection scan."""

    valid: bool
    event_count: int
    head_digest: Sha256Digest
    failure_sequence: int | None = None
    reason: str | None = None

    @property
    def is_valid(self) -> bool:
        """Compatibility-friendly spelling for callers that prefer a predicate name."""

        return self.valid


class M0101EventStore:
    """Transactional, append-only registry backed by a SHA-256 event chain.

    An open instance anchors external changes to its trusted in-memory prefix.  Across a
    fresh process, detection of a coherently recomputed history requires an independently
    retained ``recovery_head_digest``; a digest read from the same database is not a trust
    anchor.
    """

    def __init__(
        self,
        database: str | Path,
        *,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
        recovery_head_digest: Sha256Digest | None = None,
    ) -> None:
        if isinstance(max_payload_bytes, bool) or max_payload_bytes < 1:
            raise ValueError("max_payload_bytes must be positive")
        self._database = str(database)
        self._max_payload_bytes = max_payload_bytes
        self._lock = threading.RLock()
        self._closed = False
        self._trusted_head_sequence: int | None = None
        self._trusted_head_digest: Sha256Digest | None = None
        self._trusted_event_count: int | None = None
        self._connection = sqlite3.connect(
            self._database,
            isolation_level=None,
            check_same_thread=False,
            timeout=30.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._configure_connection()
        self._initialize_schema()
        if recovery_head_digest is not None:
            try:
                self.recover_event_chain(recovery_head_digest)
            except BaseException:
                self.close()
                raise
            return
        verification = self.verify_event_chain()
        if not verification.valid:
            self.close()
            raise ChainIntegrityError(verification.reason or "event chain verification failed")

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def database(self) -> str:
        """Return the configured SQLite target without exposing the connection."""

        return self._database

    def close(self) -> None:
        """Close the owned connection; repeated calls are harmless."""

        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def find_replay(
        self,
        *,
        request_id: str,
        request_digest: Sha256Digest,
        event_type: EventType,
    ) -> EventRecord | None:
        """Return an exact prior request or reject request-ID reuse with new input."""

        self._validate_request_identity(request_id, request_digest)
        with self._lock, self._read_transaction():
            self._assert_open()
            self._verify_if_database_changed_locked()
            row = self._connection.execute(
                "SELECT * FROM m0101_events WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                return None
            event = self._event_from_row(row, replayed=True)
            self._assert_replay_matches(event, request_digest, event_type)
            return event

    def register_protocol(
        self,
        *,
        request_id: str,
        request_digest: Sha256Digest,
        occurred_at: datetime,
        schema: ProtocolSchema,
        payload: Mapping[str, Any],
    ) -> EventRecord:
        """Atomically append a registration and materialize its immutable projection."""

        self._validate_request_identity(request_id, request_digest)
        self._canonical_timestamp(occurred_at)
        schema_bytes = canonical_protocol_bytes(schema)
        self._check_size(schema_bytes, "protocol schema")
        schema_digest = protocol_digest(schema)
        payload_text = self._canonical_payload(
            self._prepare_registration_payload(
                payload=payload,
                schema=schema,
                schema_digest=schema_digest,
                occurred_at=occurred_at,
            )
        )
        with self._lock, self._write_transaction():
            self._assert_open()
            self._verify_before_write_locked()
            replay = self._find_replay_locked(
                request_id=request_id,
                request_digest=request_digest,
                event_type=EventType.PROTOCOL_REGISTERED,
            )
            if replay is not None:
                return replay

            row = self._connection.execute(
                """
                SELECT protocol_digest
                FROM m0101_protocols
                WHERE schema_id = ? AND version = ?
                """,
                (schema.schema_id, schema.version),
            ).fetchone()
            if row is not None and cast("str", row["protocol_digest"]) != schema_digest:
                raise ProtocolVersionConflictError(
                    f"protocol {schema.schema_id}@{schema.version} is already registered "
                    "with different content"
                )

            event = self._append_event_locked(
                event_type=EventType.PROTOCOL_REGISTERED,
                request_id=request_id,
                request_digest=request_digest,
                occurred_at=occurred_at,
                payload_text=payload_text,
            )
            if row is None:
                self._connection.execute(
                    """
                    INSERT INTO m0101_protocols (
                        schema_id,
                        version,
                        protocol_digest,
                        schema_json,
                        registration_event_digest
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        schema.schema_id,
                        schema.version,
                        schema_digest,
                        schema_bytes.decode("utf-8"),
                        event.event_digest,
                    ),
                )
            return event

    def append_evaluation(
        self,
        *,
        request_id: str,
        request_digest: Sha256Digest,
        occurred_at: datetime,
        protocol: ProtocolReference,
        payload: Mapping[str, Any],
    ) -> EventRecord:
        """Append a metadata finding event without persisting the metadata document."""

        self._validate_request_identity(request_id, request_digest)
        self._canonical_timestamp(occurred_at)
        payload_text = self._canonical_payload(
            self._prepare_evaluation_payload(
                payload=payload,
                protocol=protocol,
                occurred_at=occurred_at,
            )
        )
        with self._lock, self._write_transaction():
            self._assert_open()
            self._verify_before_write_locked()
            replay = self._find_replay_locked(
                request_id=request_id,
                request_digest=request_digest,
                event_type=EventType.METADATA_EVALUATED,
            )
            if replay is not None:
                return replay
            self._get_protocol_row_locked(
                schema_id=protocol.schema_id,
                version=protocol.version,
                expected_digest=protocol.digest,
            )
            return self._append_event_locked(
                event_type=EventType.METADATA_EVALUATED,
                request_id=request_id,
                request_digest=request_digest,
                occurred_at=occurred_at,
                payload_text=payload_text,
            )

    def get_protocol(
        self,
        schema_id: str,
        version: str,
        *,
        expected_digest: Sha256Digest | None = None,
    ) -> StoredProtocol:
        """Load an immutable schema and verify an optional content-addressed reference."""

        with self._lock, self._read_transaction():
            self._assert_open()
            self._verify_if_database_changed_locked()
            row = self._get_protocol_row_locked(
                schema_id=schema_id,
                version=version,
                expected_digest=expected_digest,
            )
            event_row = self._connection.execute(
                "SELECT * FROM m0101_events WHERE event_digest = ?",
                (row["registration_event_digest"],),
            ).fetchone()
            if event_row is None:
                raise ChainIntegrityError("protocol projection references a missing event")
            try:
                schema = ProtocolSchema.model_validate_json(cast("str", row["schema_json"]))
                reference = ProtocolReference(
                    schema_id=schema.schema_id,
                    version=schema.version,
                    digest=cast("str", row["protocol_digest"]),
                )
            except (ValueError, TypeError) as exc:
                raise ChainIntegrityError("stored protocol projection is invalid") from exc
            return StoredProtocol(
                reference=reference,
                schema=schema,
                registration_event=self._event_from_row(event_row),
            )

    def verify_event_chain(self) -> ChainVerification:
        """Scan hashes, links, ordering, checkpoint, and the protocol projection."""

        with self._lock, self._read_transaction():
            self._assert_open()
            verification = self._scan_chain_locked(
                check_checkpoint=True,
                require_trusted_prefix=self._trusted_head_sequence is not None,
            )
            if verification.valid:
                self._adopt_trusted_head(verification)
                self._observed_data_version = self._data_version()
            return verification

    def recover_event_chain(self, expected_head_digest: Sha256Digest) -> ChainVerification:
        """Recover checkpoint/projection state from a chain anchored by a trusted digest.

        Recovery never discards or rewrites events.  The caller must supply the expected
        head from an independent trusted record, which prevents blessing a truncated tail.
        """

        if (
            not isinstance(expected_head_digest, str)
            or _DIGEST_PATTERN.fullmatch(expected_head_digest) is None
        ):
            raise ValueError("expected_head_digest must be a namespaced SHA-256 digest")
        with self._lock, self._write_transaction():
            self._assert_open()
            chain = self._scan_chain_locked(check_checkpoint=False, check_projection=False)
            if not chain.valid:
                raise ChainIntegrityError(chain.reason or "event records are not recoverable")
            if chain.head_digest != expected_head_digest:
                raise ChainIntegrityError("trusted head does not match the recoverable event chain")
            self._connection.execute(
                """
                UPDATE m0101_chain_state
                SET head_sequence = ?, head_digest = ?, event_count = ?
                WHERE singleton = 1
                """,
                (chain.event_count, chain.head_digest, chain.event_count),
            )
            self._recover_protocol_projection_locked()
            verification = self._scan_chain_locked(check_checkpoint=True)
            if not verification.valid:
                raise ChainIntegrityError(verification.reason or "recovery verification failed")
            return verification

    def _configure_connection(self) -> None:
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 30000")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.execute("PRAGMA trusted_schema = OFF")
        self._connection.execute("PRAGMA journal_mode = WAL")

    def _initialize_schema(self) -> None:
        max_chars = self._max_payload_bytes
        with self._lock:
            self._connection.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS m0101_events (
                    sequence INTEGER PRIMARY KEY,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN ('protocol_registered', 'metadata_evaluated')
                    ),
                    request_id TEXT NOT NULL UNIQUE,
                    request_digest TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    previous_digest TEXT NOT NULL,
                    event_digest TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL CHECK (length(payload_json) <= {max_chars})
                );

                CREATE TABLE IF NOT EXISTS m0101_protocols (
                    schema_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    protocol_digest TEXT NOT NULL UNIQUE,
                    schema_json TEXT NOT NULL CHECK (length(schema_json) <= {max_chars}),
                    registration_event_digest TEXT NOT NULL UNIQUE,
                    PRIMARY KEY (schema_id, version),
                    FOREIGN KEY (registration_event_digest)
                        REFERENCES m0101_events(event_digest)
                );

                CREATE TABLE IF NOT EXISTS m0101_chain_state (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    head_sequence INTEGER NOT NULL CHECK (head_sequence >= 0),
                    head_digest TEXT NOT NULL,
                    event_count INTEGER NOT NULL CHECK (event_count >= 0)
                );

                INSERT OR IGNORE INTO m0101_chain_state (
                    singleton, head_sequence, head_digest, event_count
                ) VALUES (1, 0, '{GENESIS_DIGEST}', 0);

                CREATE TRIGGER IF NOT EXISTS m0101_events_no_update
                BEFORE UPDATE ON m0101_events
                BEGIN
                    SELECT RAISE(ABORT, 'M01-01 events are append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS m0101_events_no_delete
                BEFORE DELETE ON m0101_events
                BEGIN
                    SELECT RAISE(ABORT, 'M01-01 events are append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS m0101_protocols_no_update
                BEFORE UPDATE ON m0101_protocols
                BEGIN
                    SELECT RAISE(ABORT, 'M01-01 protocols are immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS m0101_protocols_no_delete
                BEFORE DELETE ON m0101_protocols
                BEGIN
                    SELECT RAISE(ABORT, 'M01-01 protocols are immutable');
                END;
                """
            )

    @contextmanager
    def _read_transaction(self) -> Iterator[None]:
        self._assert_open()
        self._connection.execute("BEGIN")
        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    @contextmanager
    def _write_transaction(self) -> Iterator[None]:
        self._assert_open()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            trusted_state = self._chain_state_locked()
            observed_data_version = self._data_version()
            self._connection.commit()
            self._observed_data_version = observed_data_version
            self._adopt_trusted_state(trusted_state)

    def _append_event_locked(
        self,
        *,
        event_type: EventType,
        request_id: str,
        request_digest: Sha256Digest,
        occurred_at: datetime,
        payload_text: str,
    ) -> EventRecord:
        state = self._chain_state_locked()
        sequence = cast("int", state["head_sequence"]) + 1
        previous_digest = cast("Sha256Digest", state["head_digest"])
        occurred_at_text = self._canonical_timestamp(occurred_at)
        payload = self._decode_payload(payload_text)
        material = self._event_material(
            sequence=sequence,
            event_type=event_type,
            request_id=request_id,
            request_digest=request_digest,
            occurred_at=occurred_at_text,
            previous_digest=previous_digest,
            payload=payload,
        )
        event_digest = sha256_digest(material)
        try:
            self._connection.execute(
                """
                INSERT INTO m0101_events (
                    sequence,
                    event_type,
                    request_id,
                    request_digest,
                    occurred_at,
                    previous_digest,
                    event_digest,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sequence,
                    event_type.value,
                    request_id,
                    request_digest,
                    occurred_at_text,
                    previous_digest,
                    event_digest,
                    payload_text,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ChainIntegrityError(
                "event append violated an immutable store constraint"
            ) from exc
        self._connection.execute(
            """
            UPDATE m0101_chain_state
            SET head_sequence = ?, head_digest = ?, event_count = ?
            WHERE singleton = 1
            """,
            (sequence, event_digest, sequence),
        )
        return EventRecord(
            sequence=sequence,
            event_type=event_type,
            request_id=request_id,
            request_digest=request_digest,
            occurred_at=occurred_at_text,
            previous_digest=previous_digest,
            event_digest=event_digest,
            payload=payload,
        )

    def _find_replay_locked(
        self,
        *,
        request_id: str,
        request_digest: Sha256Digest,
        event_type: EventType,
    ) -> EventRecord | None:
        row = self._connection.execute(
            "SELECT * FROM m0101_events WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if row is None:
            return None
        event = self._event_from_row(row, replayed=True)
        self._assert_replay_matches(event, request_digest, event_type)
        return event

    @staticmethod
    def _assert_replay_matches(
        event: EventRecord,
        request_digest: Sha256Digest,
        event_type: EventType,
    ) -> None:
        if event.request_digest != request_digest or event.event_type is not event_type:
            raise IdempotencyConflictError(
                f"request_id {event.request_id!r} was already used for different input"
            )

    @staticmethod
    def _validate_request_identity(request_id: str, request_digest: Sha256Digest) -> None:
        if not isinstance(request_id, str) or _IDENTIFIER_PATTERN.fullmatch(request_id) is None:
            raise ValueError("request_id must be a valid M01-01 identifier")
        if not isinstance(request_digest, str) or _DIGEST_PATTERN.fullmatch(request_digest) is None:
            raise ValueError("request_digest must be a namespaced SHA-256 digest")

    def _get_protocol_row_locked(
        self,
        *,
        schema_id: str,
        version: str,
        expected_digest: Sha256Digest | None,
    ) -> sqlite3.Row:
        row = self._connection.execute(
            """
            SELECT * FROM m0101_protocols
            WHERE schema_id = ? AND version = ?
            """,
            (schema_id, version),
        ).fetchone()
        if row is None:
            raise ProtocolNotFoundError(f"protocol {schema_id}@{version} is not registered")
        if expected_digest is not None and cast("str", row["protocol_digest"]) != expected_digest:
            raise ProtocolVersionConflictError(
                f"protocol reference digest does not match {schema_id}@{version}"
            )
        return cast("sqlite3.Row", row)

    def _verify_before_write_locked(self) -> None:
        if self._data_version() != self._observed_data_version:
            verification = self._scan_chain_locked(
                check_checkpoint=True,
                require_trusted_prefix=True,
            )
        else:
            verification = self._verify_head_locked()
        if not verification.valid:
            raise ChainIntegrityError(verification.reason or "event chain verification failed")
        self._adopt_trusted_head(verification)
        self._observed_data_version = self._data_version()

    def _verify_if_database_changed_locked(self) -> None:
        if self._data_version() == self._observed_data_version:
            return
        verification = self._scan_chain_locked(
            check_checkpoint=True,
            require_trusted_prefix=True,
        )
        if not verification.valid:
            raise ChainIntegrityError(verification.reason or "event chain verification failed")
        self._adopt_trusted_head(verification)
        self._observed_data_version = self._data_version()

    def _verify_head_locked(self) -> ChainVerification:
        if (
            self._trusted_head_sequence is None
            or self._trusted_head_digest is None
            or self._trusted_event_count is None
        ):
            return ChainVerification(
                valid=False,
                event_count=0,
                head_digest=GENESIS_DIGEST,
                reason="trusted in-memory chain head is unavailable",
            )
        state = self._chain_state_locked()
        count = cast("int", state["event_count"])
        head_sequence = cast("int", state["head_sequence"])
        head_digest = cast("Sha256Digest", state["head_digest"])
        if (
            count != head_sequence
            or count != self._trusted_event_count
            or head_sequence != self._trusted_head_sequence
            or head_digest != self._trusted_head_digest
        ):
            return ChainVerification(
                valid=False,
                event_count=count,
                head_digest=head_digest,
                reason="chain checkpoint diverged from the trusted in-memory head",
            )
        row = self._connection.execute(
            "SELECT * FROM m0101_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if row is None:
            if count == 0 and head_digest == GENESIS_DIGEST:
                return ChainVerification(
                    valid=True,
                    event_count=0,
                    head_digest=GENESIS_DIGEST,
                )
            return ChainVerification(
                valid=False,
                event_count=count,
                head_digest=head_digest,
                reason="chain head event is missing",
            )
        if cast("int", row["sequence"]) != head_sequence or row["event_digest"] != head_digest:
            return ChainVerification(
                valid=False,
                event_count=count,
                head_digest=head_digest,
                failure_sequence=head_sequence,
                reason="chain head does not match its checkpoint",
            )
        failure = self._verify_event_row(row, expected_sequence=head_sequence)
        if failure is not None:
            return ChainVerification(
                valid=False,
                event_count=count,
                head_digest=head_digest,
                failure_sequence=head_sequence,
                reason=failure,
            )
        return ChainVerification(valid=True, event_count=count, head_digest=head_digest)

    def _scan_chain_locked(
        self,
        *,
        check_checkpoint: bool,
        check_projection: bool = True,
        require_trusted_prefix: bool = False,
    ) -> ChainVerification:
        previous_digest = GENESIS_DIGEST
        event_count = 0
        schema_failure = self._verify_storage_schema_locked()
        if schema_failure is not None:
            return ChainVerification(
                valid=False,
                event_count=event_count,
                head_digest=previous_digest,
                reason=schema_failure,
            )
        controls_failure = self._verify_append_only_controls_locked()
        if controls_failure is not None:
            return ChainVerification(
                valid=False,
                event_count=event_count,
                head_digest=previous_digest,
                reason=controls_failure,
            )
        registration_events: dict[tuple[str, str], tuple[str, str, str]] = {}
        seen_request_ids: set[str] = set()
        rows = self._connection.execute("SELECT * FROM m0101_events ORDER BY sequence")
        for row in rows:
            sequence = event_count + 1
            if cast("int", row["sequence"]) != sequence:
                return ChainVerification(
                    valid=False,
                    event_count=event_count,
                    head_digest=previous_digest,
                    failure_sequence=cast("int", row["sequence"]),
                    reason="event sequence contains a deletion or reordering",
                )
            if cast("str", row["previous_digest"]) != previous_digest:
                return ChainVerification(
                    valid=False,
                    event_count=event_count,
                    head_digest=previous_digest,
                    failure_sequence=sequence,
                    reason="event previous-digest link is broken",
                )
            failure = self._verify_event_row(row, expected_sequence=sequence)
            if failure is not None:
                return ChainVerification(
                    valid=False,
                    event_count=event_count,
                    head_digest=previous_digest,
                    failure_sequence=sequence,
                    reason=failure,
                )
            request_id = cast("str", row["request_id"])
            if request_id in seen_request_ids:
                return ChainVerification(
                    valid=False,
                    event_count=event_count,
                    head_digest=previous_digest,
                    failure_sequence=sequence,
                    reason="event log contains a duplicate request identifier",
                )
            seen_request_ids.add(request_id)
            previous_digest = cast("Sha256Digest", row["event_digest"])
            event_count = sequence
            if (
                require_trusted_prefix
                and sequence == self._trusted_head_sequence
                and previous_digest != self._trusted_head_digest
            ):
                return ChainVerification(
                    valid=False,
                    event_count=event_count,
                    head_digest=previous_digest,
                    failure_sequence=sequence,
                    reason="event history diverged before the trusted in-memory head",
                )
            if row["event_type"] == EventType.PROTOCOL_REGISTERED.value:
                try:
                    payload = self._decode_payload(cast("str", row["payload_json"]))
                    reference = ProtocolReference.model_validate_json(
                        canonical_json_bytes(payload["protocol"])
                    )
                    schema = ProtocolSchema.model_validate_json(
                        canonical_json_bytes(payload["protocol_schema"])
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    return ChainVerification(
                        valid=False,
                        event_count=event_count,
                        head_digest=previous_digest,
                        failure_sequence=sequence,
                        reason=f"registration payload is invalid: {exc}",
                    )
                key = (reference.schema_id, reference.version)
                schema_digest = protocol_digest(schema)
                if (
                    reference.schema_id != schema.schema_id
                    or reference.version != schema.version
                    or reference.digest != schema_digest
                ):
                    return ChainVerification(
                        valid=False,
                        event_count=event_count,
                        head_digest=previous_digest,
                        failure_sequence=sequence,
                        reason="registration protocol reference and schema are inconsistent",
                    )
                schema_text = canonical_protocol_bytes(schema).decode("utf-8")
                projection = (reference.digest, schema_text, previous_digest)
                prior = registration_events.get(key)
                if prior is None:
                    registration_events[key] = projection
                elif prior[:2] != projection[:2]:
                    return ChainVerification(
                        valid=False,
                        event_count=event_count,
                        head_digest=previous_digest,
                        failure_sequence=sequence,
                        reason="registration events conflict for one schema version",
                    )
            elif row["event_type"] == EventType.METADATA_EVALUATED.value:
                try:
                    payload = self._decode_payload(cast("str", row["payload_json"]))
                    reference = ProtocolReference.model_validate_json(
                        canonical_json_bytes(payload["protocol"])
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    return ChainVerification(
                        valid=False,
                        event_count=event_count,
                        head_digest=previous_digest,
                        failure_sequence=sequence,
                        reason=f"evaluation protocol reference is invalid: {exc}",
                    )
                registered = registration_events.get((reference.schema_id, reference.version))
                if registered is None or registered[0] != reference.digest:
                    return ChainVerification(
                        valid=False,
                        event_count=event_count,
                        head_digest=previous_digest,
                        failure_sequence=sequence,
                        reason="evaluation references an unregistered protocol",
                    )

        if (
            require_trusted_prefix
            and self._trusted_head_sequence is not None
            and event_count < self._trusted_head_sequence
        ):
            return ChainVerification(
                valid=False,
                event_count=event_count,
                head_digest=previous_digest,
                reason="event history was truncated before the trusted in-memory head",
            )
        if check_checkpoint:
            state = self._chain_state_locked()
            if (
                cast("int", state["head_sequence"]) != event_count
                or cast("int", state["event_count"]) != event_count
                or cast("str", state["head_digest"]) != previous_digest
            ):
                return ChainVerification(
                    valid=False,
                    event_count=event_count,
                    head_digest=previous_digest,
                    reason="event chain checkpoint does not match the log",
                )
        if check_projection:
            projection_failure = self._verify_projection_locked(registration_events)
            if projection_failure is not None:
                return ChainVerification(
                    valid=False,
                    event_count=event_count,
                    head_digest=previous_digest,
                    reason=projection_failure,
                )
        return ChainVerification(
            valid=True,
            event_count=event_count,
            head_digest=previous_digest,
        )

    def _verify_storage_schema_locked(self) -> str | None:
        rows = self._connection.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN ('m0101_events', 'm0101_protocols', 'm0101_chain_state')
            """
        ).fetchall()
        expected_sql = {
            name: _normalized_sql(sql)
            for name, sql in _expected_table_sql(self._max_payload_bytes).items()
        }
        actual_sql: dict[str, str] = {}
        for row in rows:
            name: Any = row["name"]
            sql: Any = row["sql"]
            if not isinstance(name, str) or not isinstance(sql, str):
                return "ledger table definition is unreadable"
            actual_sql[name] = _normalized_sql(sql)
        if actual_sql != expected_sql:
            return "ledger table definitions or constraints are missing or altered"

        for table, expected_columns in _EXPECTED_COLUMNS.items():
            columns = self._connection.execute(
                """
                SELECT name, type, "notnull" AS is_not_null, pk
                FROM pragma_table_info(?)
                ORDER BY cid
                """,
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
                """
                SELECT name, "unique" AS is_unique
                FROM pragma_index_list(?)
                """,
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

        foreign_keys = self._connection.execute(
            """
            SELECT "table", "from", "to", on_update, on_delete
            FROM pragma_foreign_key_list('m0101_protocols')
            ORDER BY id, seq
            """
        ).fetchall()
        actual_foreign_keys = tuple(
            (
                cast("str", foreign_key["table"]),
                cast("str", foreign_key["from"]),
                cast("str", foreign_key["to"]),
                cast("str", foreign_key["on_update"]),
                cast("str", foreign_key["on_delete"]),
            )
            for foreign_key in foreign_keys
        )
        if actual_foreign_keys != _EXPECTED_PROTOCOL_FOREIGN_KEYS:
            return "ledger foreign-key contract is altered"
        if self._connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            return "ledger foreign-key integrity check failed"
        return None

    def _verify_append_only_controls_locked(self) -> str | None:
        rows = self._connection.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'trigger'
              AND tbl_name IN ('m0101_events', 'm0101_protocols')
            """
        ).fetchall()
        actual = {
            cast("str", row["name"]): _normalized_sql(cast("str", row["sql"])) for row in rows
        }
        expected = {name: _normalized_sql(sql) for name, sql in _EXPECTED_TRIGGER_SQL.items()}
        if actual != expected:
            return "append-only database controls are missing or altered"
        return None

    def _verify_event_row(self, row: sqlite3.Row, *, expected_sequence: int) -> str | None:
        try:
            event_type = EventType(cast("str", row["event_type"]))
            request_id: Any = row["request_id"]
            request_digest: Any = row["request_digest"]
            previous_digest: Any = row["previous_digest"]
            event_digest: Any = row["event_digest"]
            occurred_at_text: Any = row["occurred_at"]
            payload_text: Any = row["payload_json"]
            self._validate_request_identity(request_id, request_digest)
            if (
                not isinstance(previous_digest, str)
                or _DIGEST_PATTERN.fullmatch(previous_digest) is None
                or not isinstance(event_digest, str)
                or _DIGEST_PATTERN.fullmatch(event_digest) is None
            ):
                return "event chain contains a malformed digest"
            if not isinstance(occurred_at_text, str):
                return "event occurrence time is not text"
            occurred_at = datetime.fromisoformat(occurred_at_text)
            if self._canonical_timestamp(occurred_at) != occurred_at_text:
                return "event occurrence time is not canonical"
            if not isinstance(payload_text, str):
                return "event payload is not text"
            self._check_size(payload_text.encode("utf-8"), "stored event payload")
            payload = self._decode_payload(payload_text)
            if canonical_json_bytes(payload).decode("utf-8") != payload_text:
                return "event payload is not canonical JSON"
            if event_type is EventType.PROTOCOL_REGISTERED:
                schema = ProtocolSchema.model_validate_json(
                    canonical_json_bytes(payload["protocol_schema"])
                )
                normalized_payload = self._prepare_registration_payload(
                    payload=payload,
                    schema=schema,
                    schema_digest=protocol_digest(schema),
                    occurred_at=occurred_at,
                )
            else:
                protocol = ProtocolReference.model_validate_json(
                    canonical_json_bytes(payload["protocol"])
                )
                normalized_payload = self._prepare_evaluation_payload(
                    payload=payload,
                    protocol=protocol,
                    occurred_at=occurred_at,
                )
            if canonical_json_bytes(normalized_payload).decode("utf-8") != payload_text:
                return "event payload is not in its semantic canonical form"
            material = self._event_material(
                sequence=expected_sequence,
                event_type=event_type,
                request_id=request_id,
                request_digest=request_digest,
                occurred_at=occurred_at_text,
                previous_digest=previous_digest,
                payload=payload,
            )
            expected_digest = sha256_digest(material)
        except (
            EventStoreError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            return f"event cannot be decoded: {exc}"
        if event_digest != expected_digest:
            return "event digest does not match its canonical content"
        return None

    def _verify_projection_locked(
        self,
        expected: Mapping[tuple[str, str], tuple[str, str, str]],
    ) -> str | None:
        rows = self._connection.execute(
            "SELECT * FROM m0101_protocols ORDER BY schema_id, version"
        ).fetchall()
        if len(rows) != len(expected):
            return "protocol projection count does not match registration events"
        for row in rows:
            key = (cast("str", row["schema_id"]), cast("str", row["version"]))
            projection = expected.get(key)
            actual = (
                cast("str", row["protocol_digest"]),
                cast("str", row["schema_json"]),
                cast("str", row["registration_event_digest"]),
            )
            if projection != actual:
                return (
                    f"protocol projection does not match registration event for {key[0]}@{key[1]}"
                )
        return None

    def _recover_protocol_projection_locked(self) -> None:
        # The event log is authoritative.  Recovery is permitted to rebuild this derived
        # projection only after the complete chain matches the caller's independent head.
        # DDL remains inside the surrounding transaction; event tables are never touched.
        self._connection.execute("DROP TRIGGER m0101_protocols_no_update")
        self._connection.execute("DROP TRIGGER m0101_protocols_no_delete")
        self._connection.execute("DELETE FROM m0101_protocols")
        events = self._connection.execute(
            """
            SELECT event_digest, payload_json
            FROM m0101_events
            WHERE event_type = ?
            ORDER BY sequence
            """,
            (EventType.PROTOCOL_REGISTERED.value,),
        ).fetchall()
        expected_keys: set[tuple[str, str]] = set()
        for row in events:
            payload = self._decode_payload(cast("str", row["payload_json"]))
            reference = ProtocolReference.model_validate_json(
                canonical_json_bytes(payload["protocol"])
            )
            schema = ProtocolSchema.model_validate_json(
                canonical_json_bytes(payload["protocol_schema"])
            )
            key = (reference.schema_id, reference.version)
            if key in expected_keys:
                continue
            expected_keys.add(key)
            values = (
                reference.digest,
                canonical_protocol_bytes(schema).decode("utf-8"),
                cast("str", row["event_digest"]),
            )
            self._connection.execute(
                """
                INSERT INTO m0101_protocols (
                    schema_id, version, protocol_digest, schema_json,
                    registration_event_digest
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (*key, *values),
            )
        self._connection.execute(_EXPECTED_TRIGGER_SQL["m0101_protocols_no_update"])
        self._connection.execute(_EXPECTED_TRIGGER_SQL["m0101_protocols_no_delete"])

    @staticmethod
    def _event_material(
        *,
        sequence: int,
        event_type: EventType,
        request_id: str,
        request_digest: Sha256Digest,
        occurred_at: str,
        previous_digest: Sha256Digest,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return {
            "event_type": event_type.value,
            "occurred_at": occurred_at,
            "payload": payload,
            "previous_digest": previous_digest,
            "request_digest": request_digest,
            "request_id": request_id,
            "sequence": sequence,
        }

    @staticmethod
    def _canonical_timestamp(value: datetime) -> str:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event timestamps must be timezone-aware")
        return cast("str", json.loads(canonical_json_bytes(value)))

    @staticmethod
    def _require_payload_shape(payload: Mapping[str, Any], expected: frozenset[str]) -> None:
        if not all(isinstance(key, str) for key in payload):
            raise InvalidEventPayloadError("event payload keys must be strings")
        actual = frozenset(payload)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise InvalidEventPayloadError(
                f"event payload keys do not match the closed schema; "
                f"missing={missing}, extra={extra}"
            )
        if payload["event_schema_version"] != EVENT_SCHEMA_VERSION:
            raise InvalidEventPayloadError(f"event_schema_version must be {EVENT_SCHEMA_VERSION}")

    def _prepare_registration_payload(
        self,
        *,
        payload: Mapping[str, Any],
        schema: ProtocolSchema,
        schema_digest: Sha256Digest,
        occurred_at: datetime,
    ) -> Mapping[str, Any]:
        self._require_payload_shape(payload, _REGISTRATION_PAYLOAD_KEYS)
        candidate = dict(payload)
        candidate.pop("event_schema_version")
        candidate["event_digest"] = GENESIS_DIGEST
        try:
            receipt = ProtocolSchemaReceipt.model_validate_json(canonical_json_bytes(candidate))
        except (TypeError, ValueError) as exc:
            raise InvalidEventPayloadError("registration payload is invalid") from exc
        expected_reference = ProtocolReference(
            schema_id=schema.schema_id,
            version=schema.version,
            digest=schema_digest,
        )
        if receipt.protocol != expected_reference:
            raise InvalidEventPayloadError(
                "registration protocol reference does not match the supplied schema"
            )
        if canonical_protocol_bytes(receipt.protocol_schema) != canonical_protocol_bytes(schema):
            raise InvalidEventPayloadError(
                "registration payload schema does not match the supplied schema"
            )
        if receipt.provenance.generated_at != occurred_at:
            raise InvalidEventPayloadError(
                "registration provenance time must match the event occurrence time"
            )
        normalized = receipt.model_dump(mode="python", by_alias=True, exclude_none=False)
        normalized.pop("event_digest")
        normalized["event_schema_version"] = EVENT_SCHEMA_VERSION
        normalized["protocol_schema"] = normalized_protocol(schema)
        return normalized

    def _prepare_evaluation_payload(
        self,
        *,
        payload: Mapping[str, Any],
        protocol: ProtocolReference,
        occurred_at: datetime,
    ) -> Mapping[str, Any]:
        self._require_payload_shape(payload, _EVALUATION_PAYLOAD_KEYS)
        candidate = dict(payload)
        candidate.pop("event_schema_version")
        candidate["event_digest"] = GENESIS_DIGEST
        try:
            profile = ConformanceProfile.model_validate_json(canonical_json_bytes(candidate))
        except (TypeError, ValueError) as exc:
            raise InvalidEventPayloadError("evaluation payload is invalid") from exc
        if profile.protocol != protocol:
            raise InvalidEventPayloadError(
                "evaluation protocol reference does not match the requested protocol"
            )
        if profile.evaluated_at != occurred_at or profile.provenance.generated_at != occurred_at:
            raise InvalidEventPayloadError(
                "evaluation and provenance times must match the event occurrence time"
            )
        normalized = profile.model_dump(mode="python", by_alias=True, exclude_none=False)
        normalized.pop("event_digest")
        normalized["event_schema_version"] = EVENT_SCHEMA_VERSION
        return normalized

    def _canonical_payload(self, payload: Mapping[str, Any]) -> str:
        payload_bytes = canonical_json_bytes(payload)
        self._check_size(payload_bytes, "event payload")
        return payload_bytes.decode("utf-8")

    def _decode_payload(self, payload_text: str) -> Mapping[str, Any]:
        decoded = strict_json_loads(payload_text, max_bytes=self._max_payload_bytes)
        if not isinstance(decoded, dict):
            raise TypeError("event payload must be a JSON object")
        return cast("Mapping[str, Any]", decoded)

    def _check_size(self, value: bytes, label: str) -> None:
        if len(value) > self._max_payload_bytes:
            raise PayloadTooLargeError(
                f"{label} is {len(value)} bytes; limit is {self._max_payload_bytes} bytes"
            )

    def _adopt_trusted_head(self, verification: ChainVerification) -> None:
        if not verification.valid:
            raise ChainIntegrityError("cannot trust a failed chain verification")
        self._trusted_head_sequence = verification.event_count
        self._trusted_head_digest = verification.head_digest
        self._trusted_event_count = verification.event_count

    def _adopt_trusted_state(self, state: sqlite3.Row) -> None:
        sequence = cast("int", state["head_sequence"])
        event_count = cast("int", state["event_count"])
        digest = cast("Sha256Digest", state["head_digest"])
        if sequence != event_count or _DIGEST_PATTERN.fullmatch(digest) is None:
            raise ChainIntegrityError("cannot trust an invalid chain checkpoint")
        self._trusted_head_sequence = sequence
        self._trusted_head_digest = digest
        self._trusted_event_count = event_count

    def _chain_state_locked(self) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM m0101_chain_state WHERE singleton = 1"
        ).fetchone()
        if row is None:
            raise ChainIntegrityError("event chain checkpoint is missing")
        return cast("sqlite3.Row", row)

    def _event_from_row(self, row: sqlite3.Row, *, replayed: bool = False) -> EventRecord:
        try:
            return EventRecord(
                sequence=cast("int", row["sequence"]),
                event_type=EventType(cast("str", row["event_type"])),
                request_id=cast("str", row["request_id"]),
                request_digest=cast("Sha256Digest", row["request_digest"]),
                occurred_at=cast("str", row["occurred_at"]),
                previous_digest=cast("Sha256Digest", row["previous_digest"]),
                event_digest=cast("Sha256Digest", row["event_digest"]),
                payload=self._decode_payload(cast("str", row["payload_json"])),
                replayed=replayed,
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ChainIntegrityError("stored event is invalid") from exc

    def _data_version(self) -> int:
        row = self._connection.execute("PRAGMA data_version").fetchone()
        if row is None:
            raise ChainIntegrityError("SQLite did not return a data version")
        return cast("int", row[0])

    def _assert_open(self) -> None:
        if self._closed:
            raise EventStoreError("event store is closed")

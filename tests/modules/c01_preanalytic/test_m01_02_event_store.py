"""Adversarial evidence for the immutable M01-02 resolution ledger."""

from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_02.v1 import (
    IdentityLineageResolution,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage import service
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    GENESIS_DIGEST,
    MAX_EVENT_PAYLOAD_BYTES,
    ChainIntegrityError,
    ChainVerification,
    EventRecord,
    EventStoreError,
    EventType,
    IdempotencyConflictError,
    InvalidEventPayloadError,
    M0102EventStore,
    PayloadTooLargeError,
    ResolutionConflictError,
    ResolutionNotFoundError,
    ResolutionSupersessionConflictError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.solver import (
    reconcile_identity_lineage,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

SCENARIO_PATH = Path(__file__).parents[2] / "fixtures" / "m01_02" / "scenarios.json"
SHA_F = "sha256:" + ("f" * 64)
SHA_E = "sha256:" + ("e" * 64)
SECOND_EVENT = 2
THIRD_EVENT = 3

_TRIGGER_SQL = {
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
_PRIVATE_KEYS = (
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
)
_REQUEST_ID_BY_RESOLUTION_DIGEST: dict[str, str] = {}


class _UnexpectedDatabaseAccessError(AssertionError):
    pass


def _request(
    request_id: str,
    *,
    supersedes_resolution_digest: str | None = None,
) -> ReconcileIdentityLineageRequest:
    corpus = cast(
        "dict[str, Any]",
        strict_json_loads(SCENARIO_PATH.read_bytes()),
    )
    raw = copy.deepcopy(corpus["scenarios"][0]["request"])
    raw["context"]["request_id"] = request_id
    raw["supersedes_resolution_digest"] = supersedes_resolution_digest
    return ReconcileIdentityLineageRequest.model_validate_json(json.dumps(raw))


def _resolution(
    request_id: str,
    *,
    supersedes_resolution_digest: str | None = None,
) -> IdentityLineageResolution:
    request = _request(
        request_id,
        supersedes_resolution_digest=supersedes_resolution_digest,
    )
    draft = reconcile_identity_lineage(request)
    payload = service._resolution_payload(draft, request)
    resolution = IdentityLineageResolution.model_validate(
        {**payload.model_dump(mode="python"), "event_digest": GENESIS_DIGEST},
        strict=True,
    )
    _REQUEST_ID_BY_RESOLUTION_DIGEST[resolution.resolution_digest] = request_id
    return resolution


def _payload(resolution: IdentityLineageResolution) -> dict[str, Any]:
    return resolution.model_dump(mode="json", exclude={"event_digest"})


def _append(  # noqa: PLR0913
    store: M0102EventStore,
    resolution: IdentityLineageResolution,
    *,
    request_id: str | None = None,
    request_digest: str | None = None,
    core_digest: str | None = None,
    resolution_digest: str | None = None,
    supersedes_resolution_digest: str | None = None,
    payload: dict[str, Any] | None = None,
) -> EventRecord:
    return store.append_resolution(
        request_id=request_id
        or _REQUEST_ID_BY_RESOLUTION_DIGEST[resolution.resolution_digest],
        request_digest=request_digest or resolution.request_digest,
        occurred_at=resolution.resolved_at,
        core_digest=core_digest or resolution.core_digest,
        resolution_digest=resolution_digest or resolution.resolution_digest,
        supersedes_resolution_digest=(
            resolution.supersedes_resolution_digest
            if supersedes_resolution_digest is None
            else supersedes_resolution_digest
        ),
        payload=_payload(resolution) if payload is None else payload,
    )


@contextmanager
def _mutable_ledger(database: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        for trigger_name in _TRIGGER_SQL:
            connection.execute(f"DROP TRIGGER {trigger_name}")
        try:
            yield connection
        finally:
            for trigger_sql in _TRIGGER_SQL.values():
                connection.execute(trigger_sql)


def _database_rows(database: Path, query: str) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(query).fetchall()


def _event_rows(database: Path) -> list[tuple[Any, ...]]:
    return _database_rows(database, "SELECT * FROM m0102_events ORDER BY seq")


def _trigger_definitions(database: Path) -> dict[str, str]:
    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name IN ('m0102_events','m0102_resolutions')"
        ).fetchall()
    return {name: " ".join(sql.split()) for name, sql in rows}


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value))
    return set()


def test_empty_chain_context_manager_absent_lookups_and_closed_store(tmp_path: Path) -> None:
    database = tmp_path / "empty.sqlite3"
    resolution = _resolution("request.closed")
    with M0102EventStore(database) as store:
        assert store.verify_event_chain() == ChainVerification(
            valid=True,
            event_count=0,
            head_digest=GENESIS_DIGEST,
        )
        assert (
            store.find_replay(
                request_id="request.absent",
                request_digest=SHA_F,
            )
            is None
        )
        with pytest.raises(ResolutionNotFoundError, match="not registered"):
            store.get_resolution(SHA_F)

    store.close()
    with pytest.raises(EventStoreError, match="closed"):
        store.verify_event_chain()
    with pytest.raises(EventStoreError, match="closed"):
        store.find_replay(
            request_id="request.closed",
            request_digest=resolution.request_digest,
        )
    with pytest.raises(EventStoreError, match="closed"):
        store.get_resolution(resolution.resolution_digest)
    with pytest.raises(EventStoreError, match="closed"):
        _append(store, resolution)


@pytest.mark.parametrize(
    ("request_id", "request_digest"),
    [
        (" request.invalid", SHA_F),
        ("request.invalid", "sha256:invalid"),
    ],
)
def test_find_replay_strictly_validates_lookup_identity_before_database_access(
    tmp_path: Path,
    request_id: str,
    request_digest: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with M0102EventStore(tmp_path / "invalid-replay.sqlite3") as store:

        def forbidden() -> None:
            raise _UnexpectedDatabaseAccessError

        monkeypatch.setattr(store, "_ensure_trusted", forbidden)
        with pytest.raises(ValidationError):
            store.find_replay(
                request_id=cast("Any", request_id),
                request_digest=cast("Any", request_digest),
            )


def test_append_get_exact_replay_and_canonical_public_payload(tmp_path: Path) -> None:
    database = tmp_path / "append.sqlite3"
    resolution = _resolution("request.append")
    with M0102EventStore(database) as store:
        event = _append(store, resolution)

        assert event.sequence == 1
        assert event.event_type is EventType.RESOLUTION_COMMITTED
        assert event.previous_digest == GENESIS_DIGEST
        assert event.request_digest == resolution.request_digest
        assert event.core_digest == resolution.core_digest
        assert event.resolution_digest == resolution.resolution_digest
        assert "event_digest" not in event.payload
        assert store.get_resolution(resolution.resolution_digest) == event
        assert (
            store.find_replay(
                request_id="request.append",
                request_digest=resolution.request_digest,
            )
            == event
        )
        assert _append(store, resolution) == event
        assert store.verify_event_chain() == ChainVerification(
            valid=True,
            event_count=1,
            head_digest=event.event_digest,
        )

        reconstructed = TypeAdapter(IdentityLineageResolution).validate_json(
            canonical_json_bytes({**event.payload, "event_digest": event.event_digest})
        )
        assert reconstructed.resolution_digest == resolution.resolution_digest

    payload_json = cast(
        "str",
        _database_rows(database, "SELECT payload_json FROM m0102_events")[0][0],
    )
    assert payload_json == canonical_json_bytes(_payload(resolution)).decode("utf-8")
    assert set(_PRIVATE_KEYS).isdisjoint(_all_keys(event.payload))


def test_request_id_collision_is_not_a_replay(tmp_path: Path) -> None:
    first = _resolution("request.collision")
    second = _resolution("request.different")
    with M0102EventStore(tmp_path / "collision.sqlite3") as store:
        _append(store, first)
        with pytest.raises(IdempotencyConflictError, match="reused with new content"):
            _append(store, second, request_id="request.collision")
        assert store.verify_event_chain().event_count == 1


def test_resolution_digest_collision_has_a_distinct_typed_failure(tmp_path: Path) -> None:
    resolution = _resolution("request.resolution-collision.original")
    with M0102EventStore(tmp_path / "resolution-collision.sqlite3") as store:
        original = _append(store, resolution)
        with pytest.raises(ResolutionConflictError, match="another request"):
            _append(
                store,
                resolution,
                request_id="request.resolution-collision.changed",
            )
        assert store.verify_event_chain() == ChainVerification(
            valid=True,
            event_count=1,
            head_digest=original.event_digest,
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("request_digest", "request identity"),
        ("core_digest", "semantic core"),
        ("resolution_digest", "resolution identity"),
    ],
)
def test_row_identity_must_match_the_public_payload(
    tmp_path: Path,
    field: str,
    message: str,
) -> None:
    resolution = _resolution(f"request.binding.{field}")
    overrides: dict[str, Any] = {field: SHA_F}
    with M0102EventStore(tmp_path / f"binding-{field}.sqlite3") as store:
        with pytest.raises(InvalidEventPayloadError, match=message):
            _append(store, resolution, **overrides)
        assert store.verify_event_chain().event_count == 0


def test_row_supersession_must_match_the_public_payload(tmp_path: Path) -> None:
    predecessor = _resolution("request.supersession.binding.predecessor")
    non_successor = _resolution("request.supersession.binding.candidate")
    with M0102EventStore(tmp_path / "binding-supersession.sqlite3") as store:
        _append(store, predecessor)
        with pytest.raises(InvalidEventPayloadError, match="stored supersession"):
            _append(
                store,
                non_successor,
                supersedes_resolution_digest=predecessor.resolution_digest,
            )
        assert store.verify_event_chain().event_count == 1


@pytest.mark.parametrize("forbidden_key", _PRIVATE_KEYS)
def test_private_input_material_is_rejected_before_persistence(
    tmp_path: Path,
    forbidden_key: str,
) -> None:
    resolution = _resolution(f"request.privacy.{forbidden_key}")
    payload = _payload(resolution)
    payload["nested_canary"] = {forbidden_key: "synthetic-canary"}
    with M0102EventStore(tmp_path / f"privacy-{forbidden_key}.sqlite3") as store:
        with pytest.raises(InvalidEventPayloadError, match="private input material"):
            _append(store, resolution, payload=payload)
        assert store.verify_event_chain().event_count == 0


def test_payload_byte_cap_wins_before_contract_parsing(tmp_path: Path) -> None:
    resolution = _resolution("request.oversized")
    oversized = {"not_a_resolution": "x" * MAX_EVENT_PAYLOAD_BYTES}
    with M0102EventStore(tmp_path / "oversized.sqlite3") as store:
        with pytest.raises(PayloadTooLargeError, match="byte limit"):
            _append(store, resolution, payload=oversized)
        assert store.verify_event_chain().event_count == 0


def test_sqlite_payload_constraint_counts_utf8_bytes(tmp_path: Path) -> None:
    database = tmp_path / "utf8-cap.sqlite3"
    with M0102EventStore(database):
        pass
    oversized_utf8 = "\u00e9" * ((MAX_EVENT_PAYLOAD_BYTES // 2) + 1)
    with (
        closing(sqlite3.connect(database)) as connection,
        pytest.raises(sqlite3.IntegrityError, match="CHECK constraint"),
    ):
        connection.execute(
            "INSERT INTO m0102_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                1,
                "resolution_committed",
                "request.direct",
                SHA_F,
                "2026-08-11T00:00:00.000000Z",
                SHA_F,
                SHA_E,
                None,
                oversized_utf8,
                SHA_F,
                GENESIS_DIGEST,
                SHA_E,
            ),
        )


def test_missing_supersession_is_rejected_atomically(tmp_path: Path) -> None:
    resolution = _resolution(
        "request.supersession.missing",
        supersedes_resolution_digest=SHA_F,
    )
    with M0102EventStore(tmp_path / "supersession-missing.sqlite3") as store:
        with pytest.raises(ResolutionSupersessionConflictError, match="does not exist"):
            _append(store, resolution)
        assert store.verify_event_chain().event_count == 0


def test_supersession_can_form_one_linear_chain(tmp_path: Path) -> None:
    first = _resolution("request.supersession.first")
    second = _resolution(
        "request.supersession.second",
        supersedes_resolution_digest=first.resolution_digest,
    )
    third = _resolution(
        "request.supersession.third",
        supersedes_resolution_digest=second.resolution_digest,
    )
    with M0102EventStore(tmp_path / "supersession-linear.sqlite3") as store:
        first_event = _append(store, first)
        second_event = _append(store, second)
        third_event = _append(store, third)

        assert second_event.supersedes_resolution_digest == first.resolution_digest
        assert third_event.supersedes_resolution_digest == second.resolution_digest
        assert third_event.previous_digest == second_event.event_digest
        assert store.verify_event_chain() == ChainVerification(
            valid=True,
            event_count=THIRD_EVENT,
            head_digest=third_event.event_digest,
        )
        assert first_event.sequence == 1


def test_supersession_branch_is_rejected_atomically(tmp_path: Path) -> None:
    first = _resolution("request.supersession.branch.first")
    successor = _resolution(
        "request.supersession.branch.accepted",
        supersedes_resolution_digest=first.resolution_digest,
    )
    branch = _resolution(
        "request.supersession.branch.rejected",
        supersedes_resolution_digest=first.resolution_digest,
    )
    with M0102EventStore(tmp_path / "supersession-branch.sqlite3") as store:
        _append(store, first)
        accepted = _append(store, successor)
        with pytest.raises(ResolutionSupersessionConflictError, match="already has a successor"):
            _append(store, branch)
        assert store.verify_event_chain() == ChainVerification(
            valid=True,
            event_count=SECOND_EVENT,
            head_digest=accepted.event_digest,
        )


def test_database_triggers_block_event_and_projection_mutation(tmp_path: Path) -> None:
    database = tmp_path / "triggers.sqlite3"
    resolution = _resolution("request.triggers")
    with M0102EventStore(database) as store:
        _append(store, resolution)
        with closing(sqlite3.connect(database)) as connection:
            for statement in (
                "UPDATE m0102_events SET core_digest = core_digest WHERE seq = 1",
                "DELETE FROM m0102_events WHERE seq = 1",
                "UPDATE m0102_resolutions SET core_digest = core_digest",
                "DELETE FROM m0102_resolutions",
            ):
                with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                    connection.execute(statement)
        assert store.verify_event_chain().valid


def test_exact_trigger_sql_is_attested_on_restart(tmp_path: Path) -> None:
    database = tmp_path / "trigger-attestation.sqlite3"
    with M0102EventStore(database):
        pass
    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute("DROP TRIGGER m0102_events_no_update")
        connection.execute(
            "CREATE TRIGGER m0102_events_no_update AFTER INSERT ON m0102_events "
            "BEGIN SELECT 1; END"
        )

    with pytest.raises(ChainIntegrityError, match="append-only database controls"):
        M0102EventStore(database)


def test_weakened_table_and_unique_index_contract_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "weakened-schema.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            """
            CREATE TABLE m0102_events (
                seq INTEGER,
                event_type TEXT,
                request_id TEXT,
                request_digest TEXT,
                occurred_at TEXT,
                core_digest TEXT,
                resolution_digest TEXT,
                supersedes_resolution_digest TEXT,
                payload_json TEXT,
                payload_digest TEXT,
                previous_digest TEXT,
                event_digest TEXT
            )
            """
        )

    with pytest.raises(ChainIntegrityError, match="table definitions or constraints"):
        M0102EventStore(database)


def test_malformed_preexisting_schema_fails_with_typed_sanitized_error(
    tmp_path: Path,
) -> None:
    database = tmp_path / "malformed-schema.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "CREATE TABLE m0102_chain_state(singleton INTEGER PRIMARY KEY)"
        )

    with pytest.raises(
        ChainIntegrityError,
        match="schema could not be initialized or verified",
    ) as captured:
        M0102EventStore(database)
    assert "event_count" not in str(captured.value)

    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_full_scan_detects_payload_and_event_hash_tampering(tmp_path: Path) -> None:
    payload_database = tmp_path / "tamper-payload.sqlite3"
    payload_resolution = _resolution("request.tamper.payload")
    with M0102EventStore(payload_database) as store:
        _append(store, payload_resolution)
        with _mutable_ledger(payload_database) as connection:
            connection.execute(
                "UPDATE m0102_events SET payload_json = replace(payload_json, ?, ?) WHERE seq = 1",
                ("identity_lineage_resolved", "identity_lineage_changed"),
            )
        verification = store.verify_event_chain()
        assert not verification.valid
        assert verification.reason == "event payload digest does not match"

    hash_database = tmp_path / "tamper-hash.sqlite3"
    hash_resolution = _resolution("request.tamper.hash")
    with M0102EventStore(hash_database) as store:
        _append(store, hash_resolution)
        with _mutable_ledger(hash_database) as connection:
            connection.execute(
                "UPDATE m0102_events SET event_digest = ? WHERE seq = 1",
                (SHA_F,),
            )
        verification = store.verify_event_chain()
        assert not verification.valid
        assert verification.reason == "event history was rewritten at the trusted checkpoint"


def test_full_scan_detects_noncanonical_and_duplicate_json(tmp_path: Path) -> None:
    for label, transform in (
        (
            "noncanonical",
            lambda payload: json.dumps(json.loads(payload), indent=2),
        ),
        (
            "duplicate",
            lambda payload: payload[:-1] + ',"output_type":"duplicate"}',
        ),
    ):
        database = tmp_path / f"{label}.sqlite3"
        resolution = _resolution(f"request.tamper.{label}")
        with M0102EventStore(database) as store:
            _append(store, resolution)
            payload_json = cast(
                "str",
                _database_rows(database, "SELECT payload_json FROM m0102_events")[0][0],
            )
            with _mutable_ledger(database) as connection:
                connection.execute(
                    "UPDATE m0102_events SET payload_json = ? WHERE seq = 1",
                    (transform(payload_json),),
                )
            verification = store.verify_event_chain()
            assert not verification.valid
            assert verification.reason == (
                "event ledger verification failed: InvalidEventPayloadError"
            )


def test_live_store_detects_externally_truncated_history(tmp_path: Path) -> None:
    database = tmp_path / "truncated.sqlite3"
    first = _resolution("request.truncated.first")
    second = _resolution("request.truncated.second")
    with M0102EventStore(database) as store:
        first_event = _append(store, first)
        _append(store, second)
        with _mutable_ledger(database) as connection:
            connection.execute("DELETE FROM m0102_resolutions WHERE event_seq = 2")
            connection.execute("DELETE FROM m0102_events WHERE seq = 2")
            connection.execute(
                "UPDATE m0102_chain_state SET event_count = 1, head_digest = ?",
                (first_event.event_digest,),
            )
        verification = store.verify_event_chain()
        assert not verification.valid
        assert verification.reason == "event history was truncated below the trusted checkpoint"
        with pytest.raises(ChainIntegrityError, match="truncated below"):
            store.get_resolution(first.resolution_digest)


def test_reordered_events_are_detected(tmp_path: Path) -> None:
    database = tmp_path / "reordered.sqlite3"
    first = _resolution("request.reordered.first")
    second = _resolution("request.reordered.second")
    with M0102EventStore(database) as store:
        _append(store, first)
        _append(store, second)
        with _mutable_ledger(database) as connection:
            connection.execute("UPDATE m0102_events SET seq = -1 WHERE seq = 1")
            connection.execute("UPDATE m0102_events SET seq = 1 WHERE seq = 2")
            connection.execute("UPDATE m0102_events SET seq = 2 WHERE seq = -1")
            connection.execute("UPDATE m0102_resolutions SET event_seq = -1 WHERE event_seq = 1")
            connection.execute("UPDATE m0102_resolutions SET event_seq = 1 WHERE event_seq = 2")
            connection.execute("UPDATE m0102_resolutions SET event_seq = 2 WHERE event_seq = -1")
        verification = store.verify_event_chain()
        assert not verification.valid
        assert verification.reason == "event history was rewritten at the trusted checkpoint"


def test_projection_trigger_and_checkpoint_tampering_are_detected(tmp_path: Path) -> None:
    cases = (
        (
            "projection",
            "UPDATE m0102_resolutions SET core_digest = ?",
            (SHA_F,),
            "resolution projection does not match history",
        ),
        (
            "checkpoint",
            "UPDATE m0102_chain_state SET head_digest = ? WHERE singleton = 1",
            (SHA_F,),
            "event checkpoint does not match history",
        ),
    )
    for label, statement, parameters, reason in cases:
        database = tmp_path / f"tamper-{label}.sqlite3"
        resolution = _resolution(f"request.tamper.{label}")
        with M0102EventStore(database) as store:
            _append(store, resolution)
            with _mutable_ledger(database) as connection:
                connection.execute(statement, parameters)
            verification = store.verify_event_chain()
            assert not verification.valid
            assert verification.reason == reason

    trigger_database = tmp_path / "tamper-trigger.sqlite3"
    trigger_resolution = _resolution("request.tamper.trigger")
    with M0102EventStore(trigger_database) as store:
        _append(store, trigger_resolution)
        with closing(sqlite3.connect(trigger_database, isolation_level=None)) as connection:
            connection.execute("DROP TRIGGER m0102_events_no_update")
        verification = store.verify_event_chain()
        assert not verification.valid
        assert verification.reason == "append-only database controls are missing or altered"


def test_external_connection_extension_is_adopted_via_data_version(tmp_path: Path) -> None:
    database = tmp_path / "external-extension.sqlite3"
    first = _resolution("request.external.first")
    second = _resolution("request.external.second")
    with M0102EventStore(database) as first_store:
        first_event = _append(first_store, first)
        with M0102EventStore(database) as second_store:
            second_event = _append(second_store, second)

        assert first_store.get_resolution(second.resolution_digest) == second_event
        assert first_store.verify_event_chain() == ChainVerification(
            valid=True,
            event_count=SECOND_EVENT,
            head_digest=second_event.event_digest,
        )
        assert second_event.previous_digest == first_event.event_digest


def test_post_append_data_version_refresh_stays_inside_the_process_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolution = _resolution("request.data-version.lock")
    with M0102EventStore(tmp_path / "data-version-lock.sqlite3") as store:
        original = store._read_data_version

        def asserted_locked_read() -> int:
            assert store._lock._is_owned()  # type: ignore[attr-defined]
            return original()

        monkeypatch.setattr(store, "_read_data_version", asserted_locked_read)
        event = _append(store, resolution)

        assert store.verify_event_chain().head_digest == event.event_digest


def test_missing_projection_fails_closed_without_implicit_recovery(tmp_path: Path) -> None:
    database = tmp_path / "missing-projection.sqlite3"
    resolution = _resolution("request.recovery.absent")
    with M0102EventStore(database) as store:
        _append(store, resolution)
    with _mutable_ledger(database) as connection:
        connection.execute("DELETE FROM m0102_resolutions")

    with pytest.raises(ChainIntegrityError, match="projection count"):
        M0102EventStore(database)


def test_exact_anchor_recovery_rebuilds_only_derived_state_and_triggers(
    tmp_path: Path,
) -> None:
    database = tmp_path / "anchor-recovery.sqlite3"
    first = _resolution("request.recovery.first")
    second = _resolution(
        "request.recovery.second",
        supersedes_resolution_digest=first.resolution_digest,
    )
    with M0102EventStore(database) as store:
        first_event = _append(store, first)
        second_event = _append(store, second)
    immutable_before = _event_rows(database)

    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        for trigger_name in _TRIGGER_SQL:
            connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute("DELETE FROM m0102_resolutions WHERE event_seq = 1")
        connection.execute(
            "UPDATE m0102_resolutions SET core_digest = ? WHERE event_seq = 2",
            (SHA_F,),
        )
        connection.execute(
            "INSERT INTO m0102_resolutions VALUES (?,?,?,?)",
            (SHA_F, SHA_F, 999, None),
        )
        connection.execute("DELETE FROM m0102_chain_state")
        connection.execute(
            "CREATE TRIGGER m0102_events_extra AFTER INSERT ON m0102_events "
            "BEGIN SELECT 1; END"
        )

    with M0102EventStore(
        database,
        recovery_event_count=SECOND_EVENT,
        recovery_head_digest=second_event.event_digest,
    ) as recovered:
        assert recovered.verify_event_chain() == ChainVerification(
            valid=True,
            event_count=SECOND_EVENT,
            head_digest=second_event.event_digest,
        )
        assert recovered.get_resolution(first.resolution_digest) == first_event
        assert recovered.get_resolution(second.resolution_digest) == second_event

    assert _event_rows(database) == immutable_before
    assert _database_rows(
        database,
        "SELECT resolution_digest,core_digest,event_seq,supersedes_resolution_digest "
        "FROM m0102_resolutions ORDER BY event_seq",
    ) == [
        (first.resolution_digest, first.core_digest, 1, None),
        (
            second.resolution_digest,
            second.core_digest,
            SECOND_EVENT,
            first.resolution_digest,
        ),
    ]
    assert _database_rows(
        database,
        "SELECT singleton,event_count,head_digest FROM m0102_chain_state",
    ) == [(1, SECOND_EVENT, second_event.event_digest)]
    assert _trigger_definitions(database) == {
        name: " ".join(sql.split()) for name, sql in _TRIGGER_SQL.items()
    }
    with M0102EventStore(database) as reopened:
        assert reopened.verify_event_chain().valid


@pytest.mark.parametrize(
    "damage_statement",
    [
        "DROP TABLE m0102_resolutions",
        "DROP TABLE m0102_chain_state",
        "DROP TABLE m0102_resolutions; CREATE TABLE m0102_resolutions(bad TEXT)",
        "DROP TABLE m0102_chain_state; CREATE TABLE m0102_chain_state(bad TEXT)",
    ],
)
def test_recovery_recreates_missing_or_malformed_derived_tables(
    tmp_path: Path,
    damage_statement: str,
) -> None:
    database = tmp_path / f"recovery-table-{abs(hash(damage_statement))}.sqlite3"
    resolution = _resolution("request.recovery.derived-table")
    with M0102EventStore(database) as store:
        event = _append(store, resolution)
    immutable_before = _event_rows(database)
    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        for trigger_name in _TRIGGER_SQL:
            connection.execute(f"DROP TRIGGER {trigger_name}")
        for statement in damage_statement.split("; "):
            connection.execute(statement)

    with M0102EventStore(
        database,
        recovery_event_count=1,
        recovery_head_digest=event.event_digest,
    ) as recovered:
        assert recovered.get_resolution(resolution.resolution_digest) == event
        assert recovered.verify_event_chain().valid
    assert _event_rows(database) == immutable_before


@pytest.mark.parametrize(
    ("label", "drop_statement", "view_statement"),
    [
        (
            "projection",
            "DROP TABLE m0102_resolutions",
            "CREATE VIEW m0102_resolutions AS "
            "SELECT resolution_digest,core_digest,seq AS event_seq,"
            "supersedes_resolution_digest FROM m0102_events",
        ),
        (
            "checkpoint",
            "DROP TABLE m0102_chain_state",
            "CREATE VIEW m0102_chain_state AS "
            "SELECT 1 AS singleton,0 AS event_count,'' AS head_digest",
        ),
    ],
)
def test_recovery_replaces_corrupt_derived_views_only(
    tmp_path: Path,
    label: str,
    drop_statement: str,
    view_statement: str,
) -> None:
    database = tmp_path / f"recovery-view-{label}.sqlite3"
    resolution = _resolution(f"request.recovery.view.{label}")
    with M0102EventStore(database) as store:
        event = _append(store, resolution)
    immutable_before = _event_rows(database)
    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        for trigger_name in _TRIGGER_SQL:
            connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute(drop_statement)
        connection.execute(view_statement)
        connection.execute(
            "CREATE VIEW m0102_unrelated_recovery_guard AS SELECT seq FROM m0102_events"
        )

    with M0102EventStore(
        database,
        recovery_event_count=1,
        recovery_head_digest=event.event_digest,
    ) as recovered:
        assert recovered.get_resolution(resolution.resolution_digest) == event
        assert recovered.verify_event_chain().valid

    assert _event_rows(database) == immutable_before
    assert _database_rows(
        database,
        "SELECT name,type FROM sqlite_master "
        "WHERE name IN ('m0102_resolutions','m0102_chain_state',"
        "'m0102_unrelated_recovery_guard') ORDER BY name",
    ) == [
        ("m0102_chain_state", "table"),
        ("m0102_resolutions", "table"),
        ("m0102_unrelated_recovery_guard", "view"),
    ]


def test_open_store_recovery_rebuilds_a_corrupt_checkpoint(tmp_path: Path) -> None:
    database = tmp_path / "recovery-corrupt-checkpoint.sqlite3"
    resolution = _resolution("request.recovery.corrupt-checkpoint")
    with M0102EventStore(database) as store:
        event = _append(store, resolution)
        immutable_before = _event_rows(database)
        with closing(sqlite3.connect(database, isolation_level=None)) as connection:
            connection.execute(
                "UPDATE m0102_chain_state SET event_count = ?,head_digest = ?",
                (999, SHA_F),
            )

        assert store.recover_event_chain(
            trusted_event_count=1,
            trusted_head_digest=event.event_digest,
        ) == ChainVerification(
            valid=True,
            event_count=1,
            head_digest=event.event_digest,
        )
        assert store.get_resolution(resolution.resolution_digest) == event

    assert _event_rows(database) == immutable_before
    assert _database_rows(
        database,
        "SELECT singleton,event_count,head_digest FROM m0102_chain_state",
    ) == [(1, 1, event.event_digest)]


def test_recovery_never_recreates_a_missing_immutable_event_table(tmp_path: Path) -> None:
    database = tmp_path / "recovery-missing-events.sqlite3"
    with closing(sqlite3.connect(database)):
        pass

    with pytest.raises(ChainIntegrityError, match="table definitions"):
        M0102EventStore(
            database,
            recovery_event_count=0,
            recovery_head_digest=GENESIS_DIGEST,
        )

    assert _database_rows(
        database,
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'm0102_events'",
    ) == []


def test_recovery_requires_an_exact_independent_anchor_before_writes(tmp_path: Path) -> None:
    database = tmp_path / "recovery-wrong-anchor.sqlite3"
    first = _resolution("request.recovery.anchor.first")
    second = _resolution("request.recovery.anchor.second")
    with M0102EventStore(database) as store:
        first_event = _append(store, first)
        second_event = _append(store, second)
    immutable_before = _event_rows(database)
    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute("DROP TRIGGER m0102_resolutions_no_update")
        connection.execute(
            "UPDATE m0102_resolutions SET core_digest = ? WHERE event_seq = 1",
            (SHA_F,),
        )

    for event_count, head_digest in (
        (1, first_event.event_digest),
        (SECOND_EVENT, SHA_F),
    ):
        with pytest.raises(ChainIntegrityError, match="exactly match"):
            M0102EventStore(
                database,
                recovery_event_count=event_count,
                recovery_head_digest=head_digest,
            )

    assert _event_rows(database) == immutable_before
    assert _database_rows(
        database,
        "SELECT core_digest FROM m0102_resolutions WHERE event_seq = 1",
    ) == [(SHA_F,)]
    assert second_event.sequence == SECOND_EVENT


def test_recovery_rejects_event_tamper_branch_truncation_and_invalid_payload(
    tmp_path: Path,
) -> None:
    cases = ("payload_hash", "invalid_payload", "event_type", "branch", "truncation")
    for case in cases:
        database = tmp_path / f"recovery-reject-{case}.sqlite3"
        first = _resolution(f"request.recovery.{case}.first")
        second = _resolution(
            f"request.recovery.{case}.second",
            supersedes_resolution_digest=first.resolution_digest,
        )
        third = _resolution(
            f"request.recovery.{case}.third",
            supersedes_resolution_digest=second.resolution_digest,
        )
        with M0102EventStore(database) as store:
            _append(store, first)
            _append(store, second)
            head = _append(store, third)
        with _mutable_ledger(database) as connection:
            if case == "payload_hash":
                connection.execute(
                    "UPDATE m0102_events SET payload_json = replace(payload_json, ?, ?) "
                    "WHERE seq = 1",
                    ("identity_lineage_resolved", "identity_lineage_changed"),
                )
            elif case == "invalid_payload":
                connection.execute(
                    "UPDATE m0102_events SET payload_json = ? WHERE seq = 1",
                    ("{",),
                )
            elif case == "event_type":
                connection.execute("PRAGMA ignore_check_constraints = ON")
                connection.execute(
                    "UPDATE m0102_events SET event_type = ? WHERE seq = 1",
                    ("synthetic_tamper",),
                )
            elif case == "branch":
                connection.execute(
                    "UPDATE m0102_events SET supersedes_resolution_digest = ? WHERE seq = 3",
                    (first.resolution_digest,),
                )
            else:
                connection.execute("DELETE FROM m0102_resolutions WHERE event_seq = 3")
                connection.execute("DELETE FROM m0102_events WHERE seq = 3")

        expected = {
            "payload_hash": "payload digest",
            "invalid_payload": "not recoverable",
            "event_type": "event type",
            "branch": "supersession chain",
            "truncation": "exactly match",
        }[case]
        with pytest.raises(ChainIntegrityError, match=expected):
            M0102EventStore(
                database,
                recovery_event_count=THIRD_EVENT,
                recovery_head_digest=head.event_digest,
            )


def test_recovery_preserves_live_trusted_prefix_and_closed_store_behavior(
    tmp_path: Path,
) -> None:
    database = tmp_path / "recovery-live-prefix.sqlite3"
    first = _resolution("request.recovery.live.first")
    second = _resolution("request.recovery.live.second")
    store = M0102EventStore(database)
    first_event = _append(store, first)
    _append(store, second)
    with _mutable_ledger(database) as connection:
        connection.execute("DELETE FROM m0102_resolutions WHERE event_seq = 2")
        connection.execute("DELETE FROM m0102_events WHERE seq = 2")
        connection.execute(
            "UPDATE m0102_chain_state SET event_count = 1,head_digest = ?",
            (first_event.event_digest,),
        )

    with pytest.raises(ChainIntegrityError, match="truncated below"):
        store.recover_event_chain(
            trusted_event_count=1,
            trusted_head_digest=first_event.event_digest,
        )
    store.close()
    with pytest.raises(EventStoreError, match="closed"):
        store.recover_event_chain(
            trusted_event_count=1,
            trusted_head_digest=first_event.event_digest,
        )


def test_recovery_anchor_validation_and_constructor_modes_are_closed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "recovery-anchor-validation.sqlite3"
    with M0102EventStore(database):
        pass

    for kwargs in (
        {"recovery_event_count": 0},
        {"recovery_head_digest": GENESIS_DIGEST},
    ):
        with pytest.raises(ValueError, match="supplied together"):
            M0102EventStore(database, **cast("Any", kwargs))
    with pytest.raises(ValueError, match="cannot be combined"):
        M0102EventStore(
            database,
            trusted_event_count=0,
            trusted_head_digest=GENESIS_DIGEST,
            recovery_event_count=0,
            recovery_head_digest=GENESIS_DIGEST,
        )
    for invalid_count in (True, -1, 1.0, "1"):
        with pytest.raises(ValueError, match="nonnegative integer"):
            M0102EventStore(
                database,
                recovery_event_count=cast("Any", invalid_count),
                recovery_head_digest=GENESIS_DIGEST,
            )
    with pytest.raises(ValueError, match="namespaced SHA-256"):
        M0102EventStore(
            database,
            recovery_event_count=0,
            recovery_head_digest=cast("Any", "invalid"),
        )


def test_recovery_postcondition_failure_rolls_back_all_derived_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "recovery-atomic-postcondition.sqlite3"
    resolution = _resolution("request.recovery.atomic")
    with M0102EventStore(database) as store:
        event = _append(store, resolution)
        with _mutable_ledger(database) as connection:
            connection.execute(
                "UPDATE m0102_resolutions SET core_digest = ? WHERE event_seq = 1",
                (SHA_F,),
            )

        monkeypatch.setattr(
            store,
            "_verify_locked",
            lambda: ChainVerification(
                valid=False,
                event_count=1,
                head_digest=event.event_digest,
                reason="synthetic postcondition failure",
            ),
        )
        with pytest.raises(ChainIntegrityError, match="synthetic postcondition"):
            store.recover_event_chain(
                trusted_event_count=1,
                trusted_head_digest=event.event_digest,
            )

    assert _database_rows(
        database,
        "SELECT core_digest FROM m0102_resolutions WHERE event_seq = 1",
    ) == [(SHA_F,)]


def test_external_anchor_accepts_genesis_and_a_valid_prefix_extension(tmp_path: Path) -> None:
    empty = tmp_path / "anchor-genesis.sqlite3"
    with M0102EventStore(
        empty,
        trusted_event_count=0,
        trusted_head_digest=GENESIS_DIGEST,
    ) as store:
        assert store.verify_event_chain().valid
    with pytest.raises(ChainIntegrityError, match="genesis anchor"):
        M0102EventStore(
            empty,
            trusted_event_count=0,
            trusted_head_digest=SHA_F,
        )

    extended = tmp_path / "anchor-prefix.sqlite3"
    first = _resolution("request.anchor.first")
    second = _resolution("request.anchor.second")
    with M0102EventStore(extended) as store:
        first_event = _append(store, first)
        second_event = _append(store, second)
    with M0102EventStore(
        extended,
        trusted_event_count=1,
        trusted_head_digest=first_event.event_digest,
    ) as anchored:
        assert anchored.verify_event_chain() == ChainVerification(
            valid=True,
            event_count=SECOND_EVENT,
            head_digest=second_event.event_digest,
        )


def test_external_anchor_rejects_incomplete_pair_shorter_history_and_mismatch(
    tmp_path: Path,
) -> None:
    database = tmp_path / "anchor-reject.sqlite3"
    resolution = _resolution("request.anchor.only")
    with M0102EventStore(database) as store:
        event = _append(store, resolution)

    with pytest.raises(ValueError, match="supplied together"):
        M0102EventStore(database, trusted_event_count=1)
    with pytest.raises(ValueError, match="supplied together"):
        M0102EventStore(database, trusted_head_digest=event.event_digest)
    with pytest.raises(ChainIntegrityError, match="shorter than"):
        M0102EventStore(
            database,
            trusted_event_count=SECOND_EVENT,
            trusted_head_digest=event.event_digest,
        )
    with pytest.raises(ChainIntegrityError, match="does not match"):
        M0102EventStore(
            database,
            trusted_event_count=1,
            trusted_head_digest=SHA_F,
        )


@pytest.mark.parametrize("invalid_count", [True, -1, 1.0, "1"])
def test_external_anchor_event_count_requires_an_exact_nonnegative_integer(
    tmp_path: Path,
    invalid_count: object,
) -> None:
    database = tmp_path / f"anchor-invalid-count-{type(invalid_count).__name__}.sqlite3"
    with M0102EventStore(database):
        pass

    with pytest.raises(ValueError, match="nonnegative integer"):
        M0102EventStore(
            database,
            trusted_event_count=cast("Any", invalid_count),
            trusted_head_digest=GENESIS_DIGEST,
        )


def test_unanchored_restart_cannot_authenticate_self_consistent_truncation(
    tmp_path: Path,
) -> None:
    """Document the exact local/offline limitation and the governed-anchor control."""

    database = tmp_path / "unanchored-restart.sqlite3"
    first = _resolution("request.restart.first")
    second = _resolution("request.restart.second")
    with M0102EventStore(database) as store:
        first_event = _append(store, first)
        second_event = _append(store, second)
    with _mutable_ledger(database) as connection:
        connection.execute("DELETE FROM m0102_resolutions WHERE event_seq = 2")
        connection.execute("DELETE FROM m0102_events WHERE seq = 2")
        connection.execute(
            "UPDATE m0102_chain_state SET event_count = 1, head_digest = ?",
            (first_event.event_digest,),
        )

    with M0102EventStore(database) as unanchored:
        assert unanchored.verify_event_chain() == ChainVerification(
            valid=True,
            event_count=1,
            head_digest=first_event.event_digest,
        )
    with pytest.raises(ChainIntegrityError, match="shorter than"):
        M0102EventStore(
            database,
            trusted_event_count=SECOND_EVENT,
            trusted_head_digest=second_event.event_digest,
        )

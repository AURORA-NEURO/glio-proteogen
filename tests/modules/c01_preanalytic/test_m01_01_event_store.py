from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_01.canonical import (
    canonical_protocol_bytes,
    canonical_request_digest,
)
from glio_proteogen.contracts.m01_01.v1 import (
    EvaluateMetadataRequest,
    RegisterProtocolRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    GENESIS_DIGEST,
    ChainIntegrityError,
    ChainVerification,
    EventStoreError,
    EventType,
    IdempotencyConflictError,
    InvalidEventPayloadError,
    M0101EventStore,
    PayloadTooLargeError,
    ProtocolNotFoundError,
    ProtocolVersionConflictError,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    M0101Service,
)
from tests.m01_01_support import load_request

if TYPE_CHECKING:
    from pathlib import Path

    from glio_proteogen.contracts.m01_01.v1 import (
        ConformanceProfile,
        ProtocolSchemaReceipt,
    )

_EVENT_UPDATE_TRIGGER = """
CREATE TRIGGER m0101_events_no_update
BEFORE UPDATE ON m0101_events
BEGIN
    SELECT RAISE(ABORT, 'M01-01 events are append-only');
END
"""
_EVENT_DELETE_TRIGGER = """
CREATE TRIGGER m0101_events_no_delete
BEFORE DELETE ON m0101_events
BEGIN
    SELECT RAISE(ABORT, 'M01-01 events are append-only');
END
"""
_PROTOCOL_UPDATE_TRIGGER = """
CREATE TRIGGER m0101_protocols_no_update
BEFORE UPDATE ON m0101_protocols
BEGIN
    SELECT RAISE(ABORT, 'M01-01 protocols are immutable');
END
"""
_WRONG_DIGEST = f"sha256:{'f' * 64}"
_TWO_EVENTS = 2


def _requests() -> tuple[RegisterProtocolRequest, EvaluateMetadataRequest]:
    register = load_request("register_minimal.valid.json")
    evaluate = load_request("evaluate_conformant.valid.json")
    assert isinstance(register, RegisterProtocolRequest)
    assert isinstance(evaluate, EvaluateMetadataRequest)
    return register, evaluate


def _seed(
    database: Path,
    *,
    include_evaluation: bool = True,
) -> tuple[
    M0101EventStore,
    M0101Service,
    RegisterProtocolRequest,
    EvaluateMetadataRequest,
    ProtocolSchemaReceipt,
    ConformanceProfile | None,
]:
    register, evaluate = _requests()
    store = M0101EventStore(database)
    service = M0101Service(store)
    receipt = service.register(register)
    resolved_evaluate = evaluate.model_copy(update={"protocol": receipt.protocol})
    profile = service.evaluate(resolved_evaluate) if include_evaluation else None
    return store, service, register, resolved_evaluate, receipt, profile


def _rows(database: Path, query: str) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(query).fetchall()


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*( _all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value))
    return set()


def test_context_manager_database_property_and_absent_replay(tmp_path: Path) -> None:
    database = tmp_path / "context.sqlite3"
    with M0101EventStore(database) as store:
        assert store.database == str(database)
        assert (
            store.find_replay(
                request_id="request.absent",
                request_digest=_WRONG_DIGEST,
                event_type=EventType.PROTOCOL_REGISTERED,
            )
            is None
        )
    with pytest.raises(EventStoreError, match="closed"):
        store.verify_event_chain()


def test_register_evaluate_retrieve_and_verify_without_persisting_document(tmp_path: Path) -> None:
    database = tmp_path / "ledger.sqlite3"
    store, service, register, evaluate, receipt, profile = _seed(database)
    try:
        assert profile is not None
        verification = service.verify_event_chain()
        assert verification == ChainVerification(
            valid=True,
            event_count=2,
            head_digest=profile.event_digest,
        )
        assert verification.is_valid
        assert service.get_protocol(receipt.protocol.schema_id, receipt.protocol.version) == receipt

        evaluation_event = store.find_replay(
            request_id=evaluate.context.request_id,
            request_digest=canonical_request_digest(evaluate),
            event_type=EventType.METADATA_EVALUATED,
        )
        assert evaluation_event is not None
        assert {"document", "entries", "values"}.isdisjoint(_all_keys(evaluation_event.payload))
        assert evaluation_event.payload["document_digest"] == profile.document_digest
        assert canonical_protocol_bytes(register.protocol_schema) == canonical_protocol_bytes(
            receipt.protocol_schema
        )

        encoded = TypeAdapter(ChainVerification).dump_json(verification)
        assert TypeAdapter(ChainVerification).validate_json(encoded) == verification
        assert service.evaluate(evaluate) == profile
        assert service.verify_event_chain().event_count == _TWO_EVENTS
    finally:
        service.close()


def test_exact_replay_is_idempotent_and_request_id_collision_fails(tmp_path: Path) -> None:
    database = tmp_path / "ledger.sqlite3"
    store, service, register, _, receipt, _ = _seed(database, include_evaluation=False)
    try:
        replay = service.register(register)
        assert replay.event_digest == receipt.event_digest
        assert service.verify_event_chain().event_count == 1

        changed_context = register.context.model_copy(update={"actor_id": "actor.changed"})
        changed = register.model_copy(update={"context": changed_context})
        with pytest.raises(IdempotencyConflictError, match="already used"):
            service.register(changed)
        assert service.verify_event_chain().event_count == 1

        replay_event = store.find_replay(
            request_id=register.context.request_id,
            request_digest=canonical_request_digest(register),
            event_type=EventType.PROTOCOL_REGISTERED,
        )
        assert replay_event is not None
        assert replay_event.replayed
    finally:
        service.close()


def test_request_id_cannot_cross_event_types(tmp_path: Path) -> None:
    database = tmp_path / "ledger.sqlite3"
    _, service, register, evaluate, _, _ = _seed(database, include_evaluation=False)
    try:
        reused_context = evaluate.context.model_copy(
            update={"request_id": register.context.request_id}
        )
        reused = evaluate.model_copy(update={"context": reused_context})
        with pytest.raises(IdempotencyConflictError, match="already used"):
            service.evaluate(reused)
    finally:
        service.close()


def test_same_protocol_version_rejects_changed_content_but_accepts_reordering(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ledger.sqlite3"
    _, service, register, _, receipt, _ = _seed(database, include_evaluation=False)
    try:
        reordered_schema = register.protocol_schema.model_copy(
            update={
                "fields": tuple(reversed(register.protocol_schema.fields)),
                "limitations": tuple(reversed(register.protocol_schema.limitations)),
            }
        )
        reordered_context = register.context.model_copy(
            update={"request_id": "request.synthetic.register.reordered"}
        )
        reordered = register.model_copy(
            update={"context": reordered_context, "protocol_schema": reordered_schema}
        )
        reordered_receipt = service.register(reordered)
        assert reordered_receipt.protocol.digest == receipt.protocol.digest
        assert service.verify_event_chain().event_count == _TWO_EVENTS

        changed_schema = register.protocol_schema.model_copy(update={"title": "Changed title"})
        changed_context = register.context.model_copy(
            update={"request_id": "request.synthetic.register.conflict"}
        )
        changed = register.model_copy(
            update={"context": changed_context, "protocol_schema": changed_schema}
        )
        with pytest.raises(ProtocolVersionConflictError, match="different content"):
            service.register(changed)
        assert service.verify_event_chain().event_count == _TWO_EVENTS
    finally:
        service.close()

    schema_json = _rows(database, "SELECT schema_json FROM m0101_protocols")[0][0]
    assert schema_json == canonical_protocol_bytes(register.protocol_schema).decode()


def test_closed_payload_schema_rejects_raw_metadata_and_keeps_log_unchanged(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ledger.sqlite3"
    store, service, _, evaluate, receipt, _ = _seed(database, include_evaluation=False)
    try:
        with pytest.raises(InvalidEventPayloadError, match="closed schema"):
            store.append_evaluation(
                request_id=evaluate.context.request_id,
                request_digest=canonical_request_digest(evaluate),
                occurred_at=evaluate.context.occurred_at,
                protocol=receipt.protocol,
                payload={"document": evaluate.document.model_dump(mode="python")},
            )
        assert service.verify_event_chain().event_count == 1
    finally:
        service.close()


def test_payload_byte_ceiling_is_enforced_before_append(tmp_path: Path) -> None:
    register, _ = _requests()
    schema_size = len(canonical_protocol_bytes(register.protocol_schema))
    store = M0101EventStore(tmp_path / "bounded.sqlite3", max_payload_bytes=schema_size)
    service = M0101Service(store)
    try:
        with pytest.raises(PayloadTooLargeError, match="event payload"):
            service.register(register)
        assert service.verify_event_chain().event_count == 0
    finally:
        service.close()

    with pytest.raises(ValueError, match="positive"):
        M0101EventStore(tmp_path / "zero.sqlite3", max_payload_bytes=0)
    with pytest.raises(ValueError, match="positive"):
        M0101EventStore(tmp_path / "bool.sqlite3", max_payload_bytes=True)
    schema_limited = M0101EventStore(
        tmp_path / "schema-bounded.sqlite3",
        max_payload_bytes=schema_size - 1,
    )
    schema_limited_service = M0101Service(schema_limited)
    try:
        with pytest.raises(PayloadTooLargeError, match="protocol schema"):
            schema_limited_service.register(register)
    finally:
        schema_limited_service.close()


def test_registration_payload_rejects_every_identity_mismatch(tmp_path: Path) -> None:
    database = tmp_path / "ledger.sqlite3"
    store, service, register, _, _, _ = _seed(database, include_evaluation=False)
    try:
        event = store.find_replay(
            request_id=register.context.request_id,
            request_digest=canonical_request_digest(register),
            event_type=EventType.PROTOCOL_REGISTERED,
        )
        assert event is not None
        base = json.loads(json.dumps(event.payload))

        wrong_version = {**base, "event_schema_version": "2.0.0"}
        with pytest.raises(InvalidEventPayloadError, match="event_schema_version"):
            store.register_protocol(
                request_id="request.payload.version",
                request_digest=_WRONG_DIGEST,
                occurred_at=register.context.occurred_at,
                schema=register.protocol_schema,
                payload=wrong_version,
            )

        invalid_receipt = {**base, "receipt_version": "invalid"}
        with pytest.raises(InvalidEventPayloadError, match="registration payload"):
            store.register_protocol(
                request_id="request.payload.invalid",
                request_digest=_WRONG_DIGEST,
                occurred_at=register.context.occurred_at,
                schema=register.protocol_schema,
                payload=invalid_receipt,
            )

        wrong_reference = json.loads(json.dumps(base))
        wrong_reference["protocol"]["digest"] = _WRONG_DIGEST
        with pytest.raises(InvalidEventPayloadError, match="registration payload is invalid"):
            store.register_protocol(
                request_id="request.payload.reference",
                request_digest=_WRONG_DIGEST,
                occurred_at=register.context.occurred_at,
                schema=register.protocol_schema,
                payload=wrong_reference,
            )

        wrong_schema = json.loads(json.dumps(base))
        wrong_schema["protocol_schema"]["title"] = "Different payload schema"
        with pytest.raises(InvalidEventPayloadError, match="registration payload is invalid"):
            store.register_protocol(
                request_id="request.payload.schema",
                request_digest=_WRONG_DIGEST,
                occurred_at=register.context.occurred_at,
                schema=register.protocol_schema,
                payload=wrong_schema,
            )

        non_text_key: dict[Any, Any] = dict(base)
        non_text_key[7] = "forbidden"
        with pytest.raises(InvalidEventPayloadError, match="keys must be strings"):
            store.register_protocol(
                request_id="request.payload.key",
                request_digest=_WRONG_DIGEST,
                occurred_at=register.context.occurred_at,
                schema=register.protocol_schema,
                payload=non_text_key,
            )
        assert service.verify_event_chain().event_count == 1
    finally:
        service.close()


def test_evaluation_payload_rejects_invalid_profile_reference_and_times(tmp_path: Path) -> None:
    database = tmp_path / "ledger.sqlite3"
    store, service, _, evaluate, receipt, profile = _seed(database)
    assert profile is not None
    try:
        event = store.find_replay(
            request_id=evaluate.context.request_id,
            request_digest=canonical_request_digest(evaluate),
            event_type=EventType.METADATA_EVALUATED,
        )
        assert event is not None
        base = json.loads(json.dumps(event.payload))

        invalid_profile = {**base, "profile_version": "invalid"}
        with pytest.raises(InvalidEventPayloadError, match="evaluation payload"):
            store.append_evaluation(
                request_id="request.profile.invalid",
                request_digest=_WRONG_DIGEST,
                occurred_at=evaluate.context.occurred_at,
                protocol=receipt.protocol,
                payload=invalid_profile,
            )

        wrong_protocol = receipt.protocol.model_copy(update={"digest": _WRONG_DIGEST})
        with pytest.raises(InvalidEventPayloadError, match="protocol reference"):
            store.append_evaluation(
                request_id="request.profile.protocol",
                request_digest=_WRONG_DIGEST,
                occurred_at=evaluate.context.occurred_at,
                protocol=wrong_protocol,
                payload=base,
            )

        with pytest.raises(InvalidEventPayloadError, match="times"):
            store.append_evaluation(
                request_id="request.profile.time",
                request_digest=_WRONG_DIGEST,
                occurred_at=evaluate.context.occurred_at + timedelta(seconds=1),
                protocol=receipt.protocol,
                payload=base,
            )
        assert service.verify_event_chain().event_count == _TWO_EVENTS
    finally:
        service.close()


def test_database_triggers_block_event_and_projection_mutation(tmp_path: Path) -> None:
    database = tmp_path / "ledger.sqlite3"
    _, service, _, _, _, _ = _seed(database)
    try:
        with closing(sqlite3.connect(database)) as connection:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute("DELETE FROM m0101_events WHERE sequence = 2")
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute("UPDATE m0101_protocols SET version = '2.0.0'")
        assert service.verify_event_chain().valid
    finally:
        service.close()


def test_full_scan_detects_payload_tampering(tmp_path: Path) -> None:
    database = tmp_path / "ledger.sqlite3"
    _, service, _, _, _, _ = _seed(database)
    try:
        with closing(sqlite3.connect(database, isolation_level=None)) as connection:
            connection.execute("DROP TRIGGER m0101_events_no_update")
            connection.execute(
                "UPDATE m0101_events SET request_digest = ? WHERE sequence = 2",
                (_WRONG_DIGEST,),
            )
            connection.executescript(_EVENT_UPDATE_TRIGGER)
        verification = service.verify_event_chain()
        assert not verification.valid
        assert verification.failure_sequence == _TWO_EVENTS
        assert verification.reason == "event digest does not match its canonical content"
    finally:
        service.close()


def test_persisted_payload_decoder_rejects_duplicate_json_members(tmp_path: Path) -> None:
    database = tmp_path / "duplicate-json.sqlite3"
    _, service, _, _, _, _ = _seed(database)
    try:
        with closing(sqlite3.connect(database, isolation_level=None)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM m0101_events WHERE sequence = 2"
            ).fetchone()
            assert row is not None
            duplicated_payload = (
                row["payload_json"][:-1]
                + ',"output_type":"conformance_profile"}'
            )
            material = {
                "event_type": row["event_type"],
                "occurred_at": row["occurred_at"],
                "payload": json.loads(duplicated_payload),
                "previous_digest": row["previous_digest"],
                "request_digest": row["request_digest"],
                "request_id": row["request_id"],
                "sequence": row["sequence"],
            }
            duplicated_digest = sha256_digest(material)
            connection.execute("DROP TRIGGER m0101_events_no_update")
            connection.execute(
                "UPDATE m0101_events SET payload_json = ?, event_digest = ? WHERE sequence = 2",
                (duplicated_payload, duplicated_digest),
            )
            connection.execute(
                "UPDATE m0101_chain_state SET head_digest = ? WHERE singleton = 1",
                (duplicated_digest,),
            )
            connection.executescript(_EVENT_UPDATE_TRIGGER)

        verification = service.verify_event_chain()
        assert not verification.valid
        assert verification.failure_sequence == _TWO_EVENTS
        assert verification.reason == "event cannot be decoded: duplicate JSON object key"
    finally:
        service.close()


def test_full_scan_detects_deletion_and_reordering(tmp_path: Path) -> None:
    deleted_database = tmp_path / "deleted.sqlite3"
    _, deleted_service, _, _, _, _ = _seed(deleted_database)
    try:
        with closing(sqlite3.connect(deleted_database, isolation_level=None)) as connection:
            connection.execute("DROP TRIGGER m0101_events_no_delete")
            connection.execute("DELETE FROM m0101_events WHERE sequence = 2")
            connection.executescript(_EVENT_DELETE_TRIGGER)
        deleted = deleted_service.verify_event_chain()
        assert not deleted.valid
        assert deleted.reason == "event history was truncated before the trusted in-memory head"
    finally:
        deleted_service.close()

    reordered_database = tmp_path / "reordered.sqlite3"
    _, reordered_service, _, _, _, _ = _seed(reordered_database)
    try:
        with closing(sqlite3.connect(reordered_database, isolation_level=None)) as connection:
            connection.execute("DROP TRIGGER m0101_events_no_update")
            connection.execute("UPDATE m0101_events SET sequence = sequence + 10")
            connection.executescript(_EVENT_UPDATE_TRIGGER)
        reordered = reordered_service.verify_event_chain()
        assert not reordered.valid
        assert reordered.reason == "event sequence contains a deletion or reordering"
    finally:
        reordered_service.close()


def test_coherent_external_rewrite_cannot_cross_trusted_in_memory_head(tmp_path: Path) -> None:
    database = tmp_path / "ledger.sqlite3"
    _, service, _, _, _, _ = _seed(database)
    try:
        with closing(sqlite3.connect(database, isolation_level=None)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM m0101_events WHERE sequence = 2"
            ).fetchone()
            assert row is not None
            changed_request_id = "request.synthetic.evaluate.rewritten"
            material = {
                "event_type": row["event_type"],
                "occurred_at": row["occurred_at"],
                "payload": json.loads(row["payload_json"]),
                "previous_digest": row["previous_digest"],
                "request_digest": row["request_digest"],
                "request_id": changed_request_id,
                "sequence": row["sequence"],
            }
            changed_digest = sha256_digest(material)
            connection.execute("DROP TRIGGER m0101_events_no_update")
            connection.execute(
                "UPDATE m0101_events SET request_id = ?, event_digest = ? WHERE sequence = 2",
                (changed_request_id, changed_digest),
            )
            connection.execute(
                "UPDATE m0101_chain_state SET head_digest = ? WHERE singleton = 1",
                (changed_digest,),
            )
            connection.executescript(_EVENT_UPDATE_TRIGGER)

        verification = service.verify_event_chain()
        assert not verification.valid
        assert verification.reason == "event history diverged before the trusted in-memory head"
    finally:
        service.close()


def test_rebuilt_table_cannot_remove_request_uniqueness_and_replay_an_identifier(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ledger.sqlite3"
    _, service, _, _, _, _ = _seed(database)
    service.close()

    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.row_factory = sqlite3.Row
        first = connection.execute(
            "SELECT request_id FROM m0101_events WHERE sequence = 1"
        ).fetchone()
        second = connection.execute(
            "SELECT * FROM m0101_events WHERE sequence = 2"
        ).fetchone()
        assert first is not None
        assert second is not None
        connection.executescript(
            """
            DROP TRIGGER m0101_events_no_update;
            DROP TRIGGER m0101_events_no_delete;
            ALTER TABLE m0101_events RENAME TO m0101_events_original;
            CREATE TABLE m0101_events (
                sequence INTEGER PRIMARY KEY,
                event_type TEXT NOT NULL CHECK (
                    event_type IN ('protocol_registered', 'metadata_evaluated')
                ),
                request_id TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                previous_digest TEXT NOT NULL,
                event_digest TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL CHECK (length(payload_json) <= 2097152)
            );
            INSERT INTO m0101_events SELECT * FROM m0101_events_original;
            DROP TABLE m0101_events_original;
            """
        )
        material = {
            "event_type": second["event_type"],
            "occurred_at": second["occurred_at"],
            "payload": json.loads(second["payload_json"]),
            "previous_digest": second["previous_digest"],
            "request_digest": second["request_digest"],
            "request_id": first["request_id"],
            "sequence": second["sequence"],
        }
        duplicated_head = sha256_digest(material)
        connection.execute(
            "UPDATE m0101_events SET request_id = ?, event_digest = ? WHERE sequence = 2",
            (first["request_id"], duplicated_head),
        )
        connection.execute(
            "UPDATE m0101_chain_state SET head_digest = ? WHERE singleton = 1",
            (duplicated_head,),
        )

    with pytest.raises(ChainIntegrityError, match="definitions or constraints"):
        M0101EventStore(database)


def test_external_append_is_accepted_only_when_trusted_history_remains_a_prefix(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ledger.sqlite3"
    first_store, first_service, _, evaluate, receipt, _ = _seed(
        database,
        include_evaluation=False,
    )
    second_store = M0101EventStore(database)
    second_service = M0101Service(second_store)
    try:
        profile = second_service.evaluate(evaluate)
        assert profile.protocol == receipt.protocol
        assert first_service.verify_event_chain() == ChainVerification(
            valid=True,
            event_count=2,
            head_digest=profile.event_digest,
        )
        stored_reference = first_store.get_protocol(
            receipt.protocol.schema_id,
            receipt.protocol.version,
        ).reference
        assert stored_reference == receipt.protocol
    finally:
        second_service.close()
        first_service.close()


def test_trusted_recovery_repairs_checkpoint_and_projection_without_rewriting_events(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ledger.sqlite3"
    _, service, _, _, receipt, profile = _seed(database)
    assert profile is not None
    trusted_head = profile.event_digest
    service.close()
    before = _rows(database, "SELECT * FROM m0101_events ORDER BY sequence")

    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute("DROP TABLE m0101_protocols")
        connection.execute(
            "UPDATE m0101_chain_state SET head_sequence = 0, head_digest = ?, event_count = 0",
            (GENESIS_DIGEST,),
        )

    with pytest.raises(ChainIntegrityError, match="checkpoint"):
        M0101EventStore(database)
    with pytest.raises(ChainIntegrityError, match="trusted head"):
        M0101EventStore(database, recovery_head_digest=_WRONG_DIGEST)

    recovered = M0101EventStore(database, recovery_head_digest=trusted_head)
    try:
        assert recovered.verify_event_chain() == ChainVerification(
            valid=True,
            event_count=2,
            head_digest=trusted_head,
        )
        assert recovered.get_protocol(
            receipt.protocol.schema_id,
            receipt.protocol.version,
        ).reference == receipt.protocol
    finally:
        recovered.close()
    assert _rows(database, "SELECT * FROM m0101_events ORDER BY sequence") == before


def test_trusted_recovery_rebuilds_corrupt_and_extra_projection_rows(tmp_path: Path) -> None:
    database = tmp_path / "projection-rebuild.sqlite3"
    _, service, _, _, receipt, profile = _seed(database)
    assert profile is not None
    trusted_head = profile.event_digest
    service.close()
    before = _rows(database, "SELECT * FROM m0101_events ORDER BY sequence")

    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute("DROP TRIGGER m0101_protocols_no_update")
        connection.execute("UPDATE m0101_protocols SET schema_json = '{}'")
        connection.executescript(_PROTOCOL_UPDATE_TRIGGER)
        connection.execute(
            """
            INSERT INTO m0101_protocols (
                schema_id, version, protocol_digest, schema_json,
                registration_event_digest
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "protocol.unanchored",
                "1.0.0",
                _WRONG_DIGEST,
                "{}",
                profile.event_digest,
            ),
        )

    recovered = M0101EventStore(database, recovery_head_digest=trusted_head)
    try:
        verification = recovered.verify_event_chain()
        assert verification.valid
        assert recovered.get_protocol(
            receipt.protocol.schema_id,
            receipt.protocol.version,
        ).reference == receipt.protocol
        with pytest.raises(ProtocolNotFoundError, match="not registered"):
            recovered.get_protocol("protocol.unanchored", "1.0.0")
    finally:
        recovered.close()

    assert len(_rows(database, "SELECT schema_id FROM m0101_protocols")) == 1
    assert _rows(database, "SELECT * FROM m0101_events ORDER BY sequence") == before


def test_recovery_refuses_tampered_event_even_with_matching_supplied_head(tmp_path: Path) -> None:
    database = tmp_path / "ledger.sqlite3"
    _, service, _, _, _, profile = _seed(database)
    assert profile is not None
    trusted_head = profile.event_digest
    service.close()

    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute("DROP TRIGGER m0101_events_no_update")
        connection.execute(
            "UPDATE m0101_events SET request_digest = ? WHERE sequence = 2",
            (_WRONG_DIGEST,),
        )
        connection.executescript(_EVENT_UPDATE_TRIGGER)
    with pytest.raises(ChainIntegrityError, match="digest"):
        M0101EventStore(database, recovery_head_digest=trusted_head)


def test_projection_corruption_and_altered_controls_are_detected(tmp_path: Path) -> None:
    projection_database = tmp_path / "projection.sqlite3"
    _, projection_service, _, _, _, _ = _seed(projection_database, include_evaluation=False)
    try:
        with closing(sqlite3.connect(projection_database, isolation_level=None)) as connection:
            connection.execute("DROP TRIGGER m0101_protocols_no_update")
            connection.execute(
                "UPDATE m0101_protocols SET schema_json = '{}'"
            )
            connection.executescript(_PROTOCOL_UPDATE_TRIGGER)
        projection = projection_service.verify_event_chain()
        assert not projection.valid
        assert projection.reason is not None
        assert "projection" in projection.reason
    finally:
        projection_service.close()

    controls_database = tmp_path / "controls.sqlite3"
    _, controls_service, _, _, _, _ = _seed(controls_database, include_evaluation=False)
    try:
        with closing(sqlite3.connect(controls_database, isolation_level=None)) as connection:
            connection.execute("DROP TRIGGER m0101_events_no_delete")
        controls = controls_service.verify_event_chain()
        assert not controls.valid
        assert controls.reason == "append-only database controls are missing or altered"
    finally:
        controls_service.close()


def test_missing_protocol_digest_mismatch_invalid_identity_and_closed_store(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ledger.sqlite3"
    store = M0101EventStore(database)
    with pytest.raises(ProtocolNotFoundError, match="not registered"):
        store.get_protocol("protocol.missing", "1.0.0")
    with pytest.raises(ValueError, match="request_id"):
        store.find_replay(
            request_id="not allowed spaces",
            request_digest=_WRONG_DIGEST,
            event_type=EventType.PROTOCOL_REGISTERED,
        )
    with pytest.raises(ValueError, match="request_digest"):
        store.find_replay(
            request_id="request.valid",
            request_digest="not-a-digest",
            event_type=EventType.PROTOCOL_REGISTERED,
        )
    with pytest.raises(ValueError, match="expected_head_digest"):
        store.recover_event_chain("not-a-digest")
    store.close()
    store.close()
    with pytest.raises(EventStoreError, match="closed"):
        store.verify_event_chain()

    seeded_store, service, _, _, receipt, _ = _seed(database, include_evaluation=False)
    try:
        with pytest.raises(ProtocolVersionConflictError, match="digest does not match"):
            seeded_store.get_protocol(
                receipt.protocol.schema_id,
                receipt.protocol.version,
                expected_digest=_WRONG_DIGEST,
            )
    finally:
        service.close()


def test_naive_event_timestamp_is_rejected_before_storage(tmp_path: Path) -> None:
    database = tmp_path / "source.sqlite3"
    store, service, register, _, _, _ = _seed(database, include_evaluation=False)
    try:
        event = store.find_replay(
            request_id=register.context.request_id,
            request_digest=canonical_request_digest(register),
            event_type=EventType.PROTOCOL_REGISTERED,
        )
        assert event is not None
        payload = event.payload
    finally:
        service.close()

    target = M0101EventStore(tmp_path / "target.sqlite3")
    try:
        with pytest.raises(ValueError, match="timezone-aware"):
            target.register_protocol(
                request_id="request.synthetic.naive",
                request_digest=_WRONG_DIGEST,
                occurred_at=register.context.occurred_at.replace(tzinfo=None),
                schema=register.protocol_schema,
                payload=payload,
            )
        assert target.verify_event_chain().event_count == 0
    finally:
        target.close()


def test_event_row_verifier_rejects_each_static_representation_violation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "row-representation.sqlite3"
    store, service, _, _, _, _ = _seed(database, include_evaluation=False)
    try:
        row = store._connection.execute(
            "SELECT * FROM m0101_events WHERE sequence = 1"
        ).fetchone()
        assert row is not None
        baseline = dict(row)

        malformed_digest = {**baseline, "previous_digest": "not-a-digest"}
        assert store._verify_event_row(
            malformed_digest,  # type: ignore[arg-type]
            expected_sequence=1,
        ) == "event chain contains a malformed digest"

        non_text_time = {**baseline, "occurred_at": 7}
        assert store._verify_event_row(
            non_text_time,  # type: ignore[arg-type]
            expected_sequence=1,
        ) == "event occurrence time is not text"

        noncanonical_time = {
            **baseline,
            "occurred_at": str(baseline["occurred_at"]).replace("Z", "+00:00"),
        }
        assert store._verify_event_row(
            noncanonical_time,  # type: ignore[arg-type]
            expected_sequence=1,
        ) == "event occurrence time is not canonical"

        non_text_payload = {**baseline, "payload_json": 7}
        assert store._verify_event_row(
            non_text_payload,  # type: ignore[arg-type]
            expected_sequence=1,
        ) == "event payload is not text"

        noncanonical_json = {**baseline, "payload_json": f" {baseline['payload_json']}"}
        assert store._verify_event_row(
            noncanonical_json,  # type: ignore[arg-type]
            expected_sequence=1,
        ) == "event payload is not canonical JSON"

        payload = json.loads(str(baseline["payload_json"]))
        payload["protocol_schema"]["fields"].reverse()
        semantic_noncanonical = {
            **baseline,
            "payload_json": canonical_json_bytes(payload).decode("utf-8"),
        }
        assert store._verify_event_row(
            semantic_noncanonical,  # type: ignore[arg-type]
            expected_sequence=1,
        ) == "event payload is not in its semantic canonical form"
    finally:
        service.close()


def test_internal_trust_and_decode_boundaries_fail_closed(tmp_path: Path) -> None:
    store = M0101EventStore(tmp_path / "internal-guards.sqlite3")
    try:
        with pytest.raises(TypeError, match="JSON object"):
            store._decode_payload("[]")
        with pytest.raises(ChainIntegrityError, match="failed chain verification"):
            store._adopt_trusted_head(
                ChainVerification(
                    valid=False,
                    event_count=0,
                    head_digest=GENESIS_DIGEST,
                    reason="synthetic failure",
                )
            )
        with pytest.raises(ChainIntegrityError, match="invalid chain checkpoint"):
            store._adopt_trusted_state(
                {  # type: ignore[arg-type]
                    "head_sequence": 1,
                    "event_count": 0,
                    "head_digest": GENESIS_DIGEST,
                }
            )
        invalid_row = {
            "sequence": 1,
            "event_type": "invalid",
            "request_id": "request.synthetic.invalid",
            "request_digest": _WRONG_DIGEST,
            "occurred_at": "2026-01-01T00:00:00Z",
            "previous_digest": GENESIS_DIGEST,
            "event_digest": _WRONG_DIGEST,
            "payload_json": "{}",
        }
        with pytest.raises(ChainIntegrityError, match="stored event is invalid"):
            store._event_from_row(invalid_row)  # type: ignore[arg-type]

        store._connection.execute(
            "DELETE FROM m0101_chain_state WHERE singleton = 1"
        )
        with pytest.raises(ChainIntegrityError, match="checkpoint is missing"):
            store._chain_state_locked()
    finally:
        store.close()


def test_external_change_fast_path_accepts_extension_and_rejects_tampering(
    tmp_path: Path,
) -> None:
    extended_database = tmp_path / "external-extension.sqlite3"
    first_store, first_service, _, evaluate, receipt, _ = _seed(
        extended_database,
        include_evaluation=False,
    )
    second_service = M0101Service(M0101EventStore(extended_database))
    try:
        second_service.evaluate(evaluate)
        assert first_store.get_protocol(
            receipt.protocol.schema_id,
            receipt.protocol.version,
        ).reference == receipt.protocol
    finally:
        second_service.close()
        first_service.close()

    tampered_database = tmp_path / "external-tamper.sqlite3"
    tampered_store, tampered_service, _, _, receipt, _ = _seed(
        tampered_database,
        include_evaluation=False,
    )
    try:
        with closing(sqlite3.connect(tampered_database, isolation_level=None)) as connection:
            connection.execute("DROP TRIGGER m0101_events_no_update")
            connection.execute(
                "UPDATE m0101_events SET request_digest = ? WHERE sequence = 1",
                (_WRONG_DIGEST,),
            )
            connection.executescript(_EVENT_UPDATE_TRIGGER)
        with pytest.raises(ChainIntegrityError, match="canonical content"):
            tampered_store.get_protocol(
                receipt.protocol.schema_id,
                receipt.protocol.version,
            )
    finally:
        tampered_service.close()


def test_storage_schema_and_projection_secondary_guards(tmp_path: Path) -> None:
    index_database = tmp_path / "index-contract.sqlite3"
    index_store = M0101EventStore(index_database)
    try:
        index_store._connection.execute(
            "CREATE INDEX m0101_events_request_digest_idx "
            "ON m0101_events(request_digest)"
        )
        assert index_store._verify_storage_schema_locked() is None
        index_store._connection.execute(
            "CREATE UNIQUE INDEX m0101_events_occurred_at_unique "
            "ON m0101_events(occurred_at)"
        )
        assert (
            index_store._verify_storage_schema_locked()
            == "ledger uniqueness contract is altered for m0101_events"
        )
    finally:
        index_store.close()

    foreign_key_database = tmp_path / "foreign-key.sqlite3"
    _, foreign_key_service, _, _, _, _ = _seed(
        foreign_key_database,
        include_evaluation=False,
    )
    try:
        with closing(sqlite3.connect(foreign_key_database, isolation_level=None)) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                """
                INSERT INTO m0101_protocols (
                    schema_id, version, protocol_digest, schema_json,
                    registration_event_digest
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("orphan", "1.0.0", _WRONG_DIGEST, "{}", _WRONG_DIGEST),
            )
        assert (
            foreign_key_service._store._verify_storage_schema_locked()
            == "ledger foreign-key integrity check failed"
        )
    finally:
        foreign_key_service.close()

    projection_database = tmp_path / "projection-count.sqlite3"
    _, projection_service, _, _, _, profile = _seed(projection_database)
    assert profile is not None
    try:
        with closing(sqlite3.connect(projection_database, isolation_level=None)) as connection:
            connection.execute(
                """
                INSERT INTO m0101_protocols (
                    schema_id, version, protocol_digest, schema_json,
                    registration_event_digest
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "extra",
                    "1.0.0",
                    _WRONG_DIGEST,
                    "{}",
                    profile.event_digest,
                ),
            )
        verification = projection_service.verify_event_chain()
        assert not verification.valid
        assert verification.reason == "protocol projection count does not match registration events"
    finally:
        projection_service.close()


def test_append_constraint_and_recovery_postcondition_errors_are_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "append-constraint.sqlite3"
    store, service, register, _, _, _ = _seed(database, include_evaluation=False)
    try:
        event = store.find_replay(
            request_id=register.context.request_id,
            request_digest=canonical_request_digest(register),
            event_type=EventType.PROTOCOL_REGISTERED,
        )
        assert event is not None
        payload_text = canonical_json_bytes(event.payload).decode("utf-8")
        def append_with_conflicting_sequence() -> None:
            with store._lock, store._write_transaction():
                store._connection.execute(
                    """
                    UPDATE m0101_chain_state
                    SET head_sequence = 0, head_digest = ?, event_count = 0
                    WHERE singleton = 1
                    """,
                    (GENESIS_DIGEST,),
                )
                store._append_event_locked(
                    event_type=EventType.PROTOCOL_REGISTERED,
                    request_id="request.synthetic.constraint",
                    request_digest=_WRONG_DIGEST,
                    occurred_at=register.context.occurred_at,
                    payload_text=payload_text,
                )

        with pytest.raises(ChainIntegrityError, match="immutable store constraint"):
            append_with_conflicting_sequence()
    finally:
        service.close()

    recovery = M0101EventStore(tmp_path / "recovery-postcondition.sqlite3")
    scans = iter(
        (
            ChainVerification(valid=True, event_count=0, head_digest=GENESIS_DIGEST),
            ChainVerification(
                valid=False,
                event_count=0,
                head_digest=GENESIS_DIGEST,
                reason="synthetic postcondition failure",
            ),
        )
    )
    monkeypatch.setattr(recovery, "_scan_chain_locked", lambda **_kwargs: next(scans))
    try:
        with pytest.raises(ChainIntegrityError, match="synthetic postcondition failure"):
            recovery.recover_event_chain(GENESIS_DIGEST)
    finally:
        recovery.close()


def test_registration_input_mismatches_reach_specific_guards(tmp_path: Path) -> None:
    source = tmp_path / "registration-mismatch.sqlite3"
    store, service, register, _, _, _ = _seed(source, include_evaluation=False)
    try:
        event = store.find_replay(
            request_id=register.context.request_id,
            request_digest=canonical_request_digest(register),
            event_type=EventType.PROTOCOL_REGISTERED,
        )
        assert event is not None
        supplied_schema = register.protocol_schema.model_copy(
            update={"title": "A different supplied schema"}
        )
        with pytest.raises(InvalidEventPayloadError, match="reference does not match"):
            store.register_protocol(
                request_id="request.synthetic.schema-reference",
                request_digest=_WRONG_DIGEST,
                occurred_at=register.context.occurred_at,
                schema=supplied_schema,
                payload=event.payload,
            )
        with pytest.raises(InvalidEventPayloadError, match="provenance time"):
            store.register_protocol(
                request_id="request.synthetic.registration-time",
                request_digest=_WRONG_DIGEST,
                occurred_at=register.context.occurred_at + timedelta(seconds=1),
                schema=register.protocol_schema,
                payload=event.payload,
            )
    finally:
        service.close()

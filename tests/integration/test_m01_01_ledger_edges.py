"""Focused public and defensive ledger edges not duplicated by corruption matrices."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from glio_proteogen.contracts.m01_01.canonical import canonical_request_digest
from glio_proteogen.contracts.m01_01.v1 import (
    EvaluateMetadataRequest,
    RegisterProtocolRequest,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    ChainIntegrityError,
    EventType,
    M0101EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    M0101Service,
)
from tests.m01_01_support import load_request

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration


def _requests() -> tuple[RegisterProtocolRequest, EvaluateMetadataRequest]:
    registration = load_request("register_minimal.valid.json")
    evaluation = load_request("evaluate_conformant.valid.json")
    assert isinstance(registration, RegisterProtocolRequest)
    assert isinstance(evaluation, EvaluateMetadataRequest)
    return registration, evaluation


def test_store_context_database_property_and_direct_evaluation_replay(
    tmp_path: Path,
) -> None:
    database = tmp_path / "direct-replay.sqlite3"
    registration, evaluation = _requests()

    with M0101EventStore(database) as store:
        assert store.database == str(database)
        service = M0101Service(store)
        receipt = service.register(registration)
        resolved = evaluation.model_copy(update={"protocol": receipt.protocol})
        profile = service.evaluate(resolved)
        event = store.find_replay(
            request_id=resolved.context.request_id,
            request_digest=canonical_request_digest(resolved),
            event_type=EventType.METADATA_EVALUATED,
        )
        assert event is not None

        replay = store.append_evaluation(
            request_id=resolved.context.request_id,
            request_digest=canonical_request_digest(resolved),
            occurred_at=resolved.context.occurred_at,
            protocol=receipt.protocol,
            payload=event.payload,
        )

        assert replay.replayed is True
        assert replay.event_digest == profile.event_digest
        service.close()


def test_projection_missing_event_and_invalid_schema_fail_closed(tmp_path: Path) -> None:
    registration, _ = _requests()

    missing_store = M0101EventStore(tmp_path / "missing-event.sqlite3")
    missing_service = M0101Service(missing_store)
    receipt = missing_service.register(registration)
    missing_store._connection.execute("DROP TRIGGER m0101_events_no_delete")
    missing_store._connection.execute("PRAGMA foreign_keys = OFF")
    missing_store._connection.execute("DELETE FROM m0101_events")
    try:
        with pytest.raises(ChainIntegrityError, match="references a missing event"):
            missing_store.get_protocol(receipt.protocol.schema_id, receipt.protocol.version)
    finally:
        missing_service.close()

    invalid_store = M0101EventStore(tmp_path / "invalid-projection.sqlite3")
    invalid_service = M0101Service(invalid_store)
    receipt = invalid_service.register(registration)
    invalid_store._connection.execute("DROP TRIGGER m0101_protocols_no_update")
    invalid_store._connection.execute("UPDATE m0101_protocols SET schema_json = '{}' ")
    try:
        with pytest.raises(ChainIntegrityError, match="projection is invalid"):
            invalid_store.get_protocol(receipt.protocol.schema_id, receipt.protocol.version)
    finally:
        invalid_service.close()


def test_trusted_head_defensive_states_are_explicit(tmp_path: Path) -> None:
    with M0101EventStore(tmp_path / "trusted-head.sqlite3") as store:
        store._trusted_head_sequence = None
        unavailable = store._verify_head_locked()

    assert unavailable.valid is False
    assert unavailable.reason == "trusted in-memory chain head is unavailable"

    with M0101EventStore(tmp_path / "diverged-head.sqlite3") as store:
        store._trusted_event_count = 1
        diverged = store._verify_head_locked()

    assert diverged.valid is False
    assert diverged.reason == "chain checkpoint diverged from the trusted in-memory head"

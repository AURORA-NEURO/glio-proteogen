"""Focused lifecycle and safe-failure coverage for the M01-02 service plugin."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m01_02.v1 import ReconcileIdentityLineageRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    ChainVerification,
    EventRecord,
    EventStoreError,
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.plugin import (
    M0102Plugin,
    ValidatedM0102Request,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    InvalidResolutionEventError,
    M0102Service,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import AwareDatetime

    from glio_proteogen.kernel.models import Identifier, Sha256Digest


SCENARIO_PATH = Path(__file__).parents[2] / "fixtures" / "m01_02" / "scenarios.json"
SHA_F = "sha256:" + ("f" * 64)


def _request() -> ReconcileIdentityLineageRequest:
    corpus = cast("dict[str, Any]", strict_json_loads(SCENARIO_PATH.read_bytes()))
    raw = corpus["scenarios"][0]["request"]
    return TypeAdapter(ReconcileIdentityLineageRequest).validate_json(
        canonical_json_bytes(raw),
        strict=True,
    )


@pytest.fixture
def identity_request() -> ReconcileIdentityLineageRequest:
    return _request()


@pytest.fixture
def committed_event(
    tmp_path: Path,
    identity_request: ReconcileIdentityLineageRequest,
) -> EventRecord:
    store = M0102EventStore(tmp_path / "committed.sqlite3")
    with M0102Service(store) as service:
        resolution = service.execute(identity_request)
        return store.get_resolution(resolution.resolution_digest)


@dataclass(slots=True)
class _ReplayStore:
    event: EventRecord
    closed: bool = False

    def find_replay(
        self,
        *,
        request_id: Identifier,
        request_digest: Sha256Digest,
    ) -> EventRecord | None:
        del request_id, request_digest
        return self.event

    def append_resolution(  # noqa: PLR0913 - mirrors the public store protocol
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
        del (
            request_id,
            request_digest,
            occurred_at,
            core_digest,
            resolution_digest,
            supersedes_resolution_digest,
            payload,
        )
        return self.event

    def get_resolution(self, resolution_digest: Sha256Digest) -> EventRecord:
        del resolution_digest
        return self.event

    def verify_event_chain(self) -> ChainVerification:
        return ChainVerification(
            valid=True,
            event_count=self.event.sequence,
            head_digest=self.event.event_digest,
        )

    def close(self) -> None:
        self.closed = True


def _wrong_event_type(event: EventRecord) -> EventRecord:
    return event.model_copy(update={"event_type": cast("Any", "unexpected_event")})


def _wrong_request_binding(event: EventRecord) -> EventRecord:
    return event.model_copy(update={"request_id": "request.different"})


def _embedded_event_digest(event: EventRecord) -> EventRecord:
    return event.model_copy(
        update={"payload": {**event.payload, "event_digest": event.event_digest}}
    )


def _invalid_public_payload(event: EventRecord) -> EventRecord:
    payload = dict(event.payload)
    payload.pop("decision")
    return event.model_copy(update={"payload": payload})


def _invalid_resolution_digest(event: EventRecord) -> EventRecord:
    return event.model_copy(
        update={"payload": {**event.payload, "resolution_digest": SHA_F}}
    )


def _contradictory_event_key(event: EventRecord) -> EventRecord:
    return event.model_copy(update={"core_digest": SHA_F})


def test_service_context_lifecycle_delegates_retrieval_and_verification(
    tmp_path: Path,
    identity_request: ReconcileIdentityLineageRequest,
) -> None:
    store = M0102EventStore(tmp_path / "lifecycle.sqlite3")
    service = M0102Service(store)

    with service as entered:
        resolution = entered.execute(identity_request)
        assert entered is service
        assert entered.get_resolution(resolution.resolution_digest) == resolution
        assert entered.verify_event_chain().valid

    service.close()
    with pytest.raises(EventStoreError, match="closed"):
        service.verify_event_chain()


def test_plugin_accepts_models_and_rejects_invalid_execution_tokens(
    tmp_path: Path,
    identity_request: ReconcileIdentityLineageRequest,
) -> None:
    with M0102Service(M0102EventStore(tmp_path / "plugin-lifecycle.sqlite3")) as service:
        plugin = M0102Plugin(service)
        token = plugin.validate(identity_request)

        assert isinstance(token, ValidatedM0102Request)
        assert plugin.run(token).request_digest.startswith("sha256:")
        with pytest.raises(TypeError, match="validated request token"):
            plugin.run(cast("Any", identity_request))
        with pytest.raises(ValidationError):
            plugin.validate({})


@pytest.mark.parametrize(
    ("corrupt", "message"),
    [
        (_wrong_event_type, "wrong event type"),
        (_wrong_request_binding, "does not bind the request"),
        (_embedded_event_digest, "embeds its event digest"),
        (_invalid_public_payload, "violates the public contract"),
        (_invalid_resolution_digest, "violates the public contract"),
        (_contradictory_event_key, "keys contradict its payload"),
    ],
)
def test_service_rejects_corrupt_replay_records(
    identity_request: ReconcileIdentityLineageRequest,
    committed_event: EventRecord,
    corrupt: Callable[[EventRecord], EventRecord],
    message: str,
) -> None:
    store = _ReplayStore(corrupt(committed_event))

    with pytest.raises(InvalidResolutionEventError, match=message):
        M0102Service(store).execute(identity_request)

    assert not store.closed

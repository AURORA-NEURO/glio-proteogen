"""Deterministic M26-04 runtime, abstention, and replay tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_04 import (
    AuthorizationDecision,
    GatewayStatus,
    JobStatus,
    result_identifier,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c20_biomarker_panel.m26_04_api_sdk_cli_gateway import (
    M2604AuthorizationError,
    M2604GatewayEngine,
    M2604ReplayError,
    M2604Service,
)
from tests.contract.test_m2604_contract import _request


def test_published_surface_is_deterministic_and_replayable() -> None:
    request = _request()
    engine = M2604GatewayEngine()
    first = engine.publish(request)
    second = M2604Service().publish(request.model_dump_json())
    assert first == second
    assert first.status is GatewayStatus.PUBLISHED
    assert first.access_surface is not None
    assert first.result_id == result_identifier(first.request_digest)
    assert first.support_decision.status is SupportStatus.SUPPORTED
    assert engine.replay(first) == first


def test_denied_operation_abstains_without_surface() -> None:
    request = _request()
    denied = request.authorizations[0].model_copy(update={"decision": AuthorizationDecision.DENY})
    result = M2604GatewayEngine().publish(request.model_copy(update={"authorizations": (denied,)}))
    assert result.status is GatewayStatus.ABSTAINED
    assert result.access_surface is None
    assert result.abstention_reason is not None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_unresolved_job_and_compatibility_abstain() -> None:
    request = _request()
    queued = request.jobs[0].model_copy(update={"status": JobStatus.QUEUED})
    result = M2604GatewayEngine().publish(request.model_copy(update={"jobs": (queued,)}))
    assert result.status is GatewayStatus.ABSTAINED
    assert any(item.code.value == "async_job_unbound" for item in result.findings)


def test_authorization_preflight_fails_closed_before_material() -> None:
    request = _request()
    references = request.context.references.model_copy(
        update={
            "support": request.context.references.support.model_copy(update={"state": "rejected"})
        }
    )
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    with pytest.raises(M2604AuthorizationError):
        M2604GatewayEngine().publish(denied)


def test_service_accepts_strict_json_and_rejects_tampered_replay() -> None:
    service = M2604Service()
    result = service.publish(_request().model_dump_json())
    assert service.replay(result.model_dump_json()) == result
    tampered = result.model_dump(mode="json")
    tampered["result_id"] = "gateway.m2604.forged"
    with pytest.raises((M2604ReplayError, ValidationError)):
        service.replay(tampered)


def test_mapping_and_bytes_service_paths_preserve_canonical_result() -> None:
    request = _request()
    service = M2604Service()
    from_mapping = service.publish(request.model_dump(mode="json"))
    from_bytes = service.publish(request.model_dump_json().encode())
    assert from_mapping == from_bytes

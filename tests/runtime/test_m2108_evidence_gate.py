"""Runtime, service and plugin tests for M21-08."""

from __future__ import annotations

from typing import Any, cast

import pytest

from glio_proteogen.contracts.m21_08 import (
    ApprovalDecision,
    GateRunStatus,
    RiskSeverity,
)
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m21_08_evidence_gate_release_adjudicator import (
    M2108AuthorizationError,
    M2108Engine,
    M2108EvaluationError,
    M2108Plugin,
    M2108ReplayError,
    M2108Service,
    adjudicate_complex_activity_evidence_gate,
)
from tests.adversarial.test_m2108_adversarial import _request


def test_nominal_gate_is_adjudicated_and_replayable() -> None:
    engine = M2108Engine()
    result = engine.evaluate(_request())
    assert result.status is GateRunStatus.ADJUDICATED
    assert result.release_record is not None
    assert result.release_record.decision.value == "pass"
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.emits_parent is False
    assert result.human_review_required is True
    assert engine.verify(result).result_digest == result.result_digest


@pytest.mark.parametrize(
    "update",
    [
        {"requirements": (_request().requirements[0].model_copy(update={"satisfied": False}),)},
        {"benchmarks": (_request().benchmarks[0].model_copy(update={"passed": False}),)},
        {
            "residual_risks": (
                _request()
                .residual_risks[0]
                .model_copy(update={"severity": RiskSeverity.CRITICAL, "accepted": False}),
            )
        },
        {
            "approvals": (
                _request().approvals[0].model_copy(update={"decision": ApprovalDecision.DEFER}),
            )
        },
    ],
)
def test_gate_failures_abstain_without_release_record(update: dict[str, object]) -> None:
    result = M2108Engine().evaluate(_request().model_copy(update=update))
    assert result.status is GateRunStatus.ABSTAINED
    assert result.release_record is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True
    assert result.abstention_reason is not None
    assert result.findings


@pytest.mark.parametrize(
    "field",
    ["approved_configuration", "provenance", "quality", "support", "intended_use"],
)
def test_denied_control_fails_before_gate_traversal(field: str) -> None:
    request = _request()
    decision = request.context.references.__getattribute__(field)
    denied = decision.model_copy(update={"state": UpstreamDecisionState.REJECTED})
    references = request.context.references.model_copy(update={field: denied})
    candidate = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    with pytest.raises(M2108AuthorizationError):
        M2108Engine().evaluate(candidate)


def test_consent_and_malformed_request_are_safe_failures() -> None:
    request = _request()
    consent = request.context.references.consent.model_copy(update={"state": "revoked"})
    refs = request.context.references.model_copy(update={"consent": consent})
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": refs})}
    )
    with pytest.raises(M2108AuthorizationError):
        M2108Engine().evaluate(denied)
    with pytest.raises(M2108AuthorizationError):
        M2108Engine().evaluate({"request_id": "invalid"})


def test_service_and_plugin_share_strict_parse_once_boundary() -> None:
    request = _request()
    service = M2108Service()
    validated = service.validate_request(request)
    result = service.execute(validated)
    assert service.verify(result).result_id == result.result_id

    plugin = M2108Plugin(service)
    token = plugin.validate(request.model_dump_json())
    assert plugin.run(token).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M21-08"
    with pytest.raises(TypeError):
        plugin.run(cast("Any", request))
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(object())
    with pytest.raises(TypeError):
        plugin.run(cast("Any", object()))


def test_plugin_rejects_nested_request_mutation() -> None:
    request = _request()
    plugin = M2108Plugin()
    token = plugin.validate(request)
    object.__setattr__(token.request, "request_id", "m2108.tampered")
    with pytest.raises(TypeError):
        plugin.run(token)


def test_replay_rejects_payload_and_request_tampering() -> None:
    engine = M2108Engine()
    result = engine.evaluate(_request())
    with pytest.raises(M2108ReplayError):
        engine.verify(result.model_copy(update={"abstention_reason": "tampered"}), replay=False)
    changed = _request().model_copy(update={"request_id": "request.m2108.changed"})
    with pytest.raises(M2108ReplayError):
        engine.verify(result.model_copy(update={"request": changed}), replay=False)


def test_public_function_and_invalid_result_are_closed() -> None:
    result = adjudicate_complex_activity_evidence_gate(_request())
    assert result.status is GateRunStatus.ADJUDICATED
    with pytest.raises(M2108ReplayError):
        M2108Engine().verify({"result_id": "invalid"})
    invalid = _request().model_dump(mode="python")
    invalid.pop("benchmarks")
    with pytest.raises(M2108EvaluationError):
        M2108Engine().evaluate(invalid)

"""Runtime, service, replay, and strict plugin tests for M24-08."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m24_08 import (
    ApprovalDecision,
    GateDecision,
    GateFindingCode,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ContextReferences,
    ControlRole,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c21_reference_material.m24_08_evidence_gate_release_adjudicator import (
    EvidenceGateSubmission,
    M2408AuthorizationError,
    M2408EvidenceGateEngine,
    M2408Plugin,
    M2408ReplayError,
    M2408Service,
    M2408TokenError,
    adjudicate_biomarker_panel_evidence_gate,
)
from tests.contract.test_m2408_deep import _request


def _denied_controls() -> ContextReferences:
    request = _request()
    current = request.context.references
    denied_support = UpstreamDecisionReference(
        decision_id="m2408.decision.support-denied",
        state=UpstreamDecisionState.REJECTED,
        policy_version="0.1.0",
        evidence=current.support.evidence,
    )
    return current.model_copy(update={"support": denied_support})


def test_engine_emits_closed_adjudication_and_replays_byte_identically() -> None:
    request = _request()
    result = M2408EvidenceGateEngine().adjudicate(request)

    assert result.status.value == "adjudicated"
    assert result.release_record is not None
    assert result.release_record.decision is GateDecision.PASS
    assert result.parent_target == "biomarker panel"
    assert result.emits_parent is False
    assert len(result.provenance.control_decisions) == len(tuple(ControlRole))
    assert result.support_decision.status.value == "supported"
    assert result.result_id.startswith("gate.m2408.")
    assert M2408EvidenceGateEngine().replay(result) == result


@pytest.mark.parametrize(
    ("candidate", "decision", "finding"),
    [
        (_request(satisfied=False), GateDecision.BLOCK, GateFindingCode.REQUIREMENT_UNSATISFIED),
        (_request(benchmark_passed=False), GateDecision.BLOCK, GateFindingCode.BENCHMARK_FAILED),
        (
            _request(approval_decision=ApprovalDecision.DEFER),
            GateDecision.REVIEW_REQUIRED,
            GateFindingCode.APPROVAL_MISSING,
        ),
    ],
)
def test_gate_decision_and_findings_preserve_caller_declared_failures(
    candidate: object, decision: GateDecision, finding: GateFindingCode
) -> None:
    result = adjudicate_biomarker_panel_evidence_gate(candidate)

    assert result.release_record is not None
    assert result.release_record.decision is decision
    assert any(item.code is finding for item in result.findings)
    assert result.support_decision.status.value == "supported"
    assert result.human_review_required is True


def test_authorization_fails_closed_before_gate_material_is_read() -> None:
    request = _request()
    denied = request.context.model_copy(update={"references": _denied_controls()})
    denied_request = request.model_copy(update={"context": denied})

    with pytest.raises(M2408AuthorizationError):
        M2408EvidenceGateEngine().adjudicate(denied_request)
    with pytest.raises(M2408AuthorizationError):
        M2408EvidenceGateEngine().adjudicate({"context": {"references": {}}})


def test_service_accepts_mapping_and_strict_canonical_json() -> None:
    service = M2408Service()
    request = _request()
    encoded = canonical_json_bytes(request.model_dump(mode="json"))

    from_mapping = service.adjudicate(request.model_dump(mode="json"))
    from_json = service.adjudicate(encoded)

    assert from_mapping == from_json
    assert service.replay(from_json.model_dump(mode="json")) == from_json
    assert service.descriptor["module_id"] == "GLIO-PROTEOGEN-M24-08"
    assert service.descriptor["unsupported_to_negative"] is False


def test_plugin_requires_capability_token_and_supports_string_submission() -> None:
    plugin = M2408Plugin()
    request = _request()
    payload = canonical_json_bytes(request.model_dump(mode="json"))
    token = plugin.validate(EvidenceGateSubmission(payload))
    result = plugin.run(token)

    assert result.request.request_id == request.request_id
    assert plugin.replay(result.model_dump(mode="json")) == result
    with pytest.raises(M2408TokenError):
        plugin.run(object())  # type: ignore[arg-type]


def test_replay_rejects_tampered_result_and_tampered_request() -> None:
    result = M2408EvidenceGateEngine().adjudicate(_request())
    tampered_result = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    tampered_request = result.request.model_copy(update={"request_id": "m2408.request.tampered"})
    tampered_request_result = result.model_copy(update={"request": tampered_request})

    with pytest.raises(M2408ReplayError):
        M2408EvidenceGateEngine().replay(tampered_result)
    with pytest.raises(M2408ReplayError):
        M2408EvidenceGateEngine().replay(tampered_request_result)


def test_descriptor_declares_boundaries_without_claim_inflation() -> None:
    descriptor = M2408Plugin().descriptor

    assert descriptor.parent_target == "biomarker panel"
    assert descriptor.provisional_abi is True
    assert descriptor.traceability is True
    assert descriptor.risk_controls is True
    assert descriptor.unsupported_to_negative is False
    assert descriptor.kinase_activity is False
    assert descriptor.all_omics_fusion is False
    assert descriptor.treatment_recommendation is False
    assert descriptor.identity_inference is False
    assert descriptor.consent_inference is False



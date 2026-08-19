"""Runtime, service, replay, and strict plugin tests for M23-08."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m23_08 import (
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
from glio_proteogen.modules.c21_reference_material.m23_08_evidence_gate_release_adjudicator import (
    EvidenceGateSubmission,
    M2308AuthorizationError,
    M2308EvidenceGateEngine,
    M2308Plugin,
    M2308ReplayError,
    M2308Service,
    M2308TokenError,
    ValidatedM2308Request,
    adjudicate_variant_peptide_evidence_gate,
)
from tests.contract.test_m2308_deep import _request


def _denied_controls() -> ContextReferences:
    request = _request()
    current = request.context.references
    denied_support = UpstreamDecisionReference(
        decision_id="m2308.decision.support-denied",
        state=UpstreamDecisionState.REJECTED,
        policy_version="0.1.0",
        evidence=current.support.evidence,
    )
    return current.model_copy(update={"support": denied_support})


def test_engine_emits_closed_adjudication_and_replays_byte_identically() -> None:
    request = _request()
    result = M2308EvidenceGateEngine().adjudicate(request)

    assert result.status.value == "adjudicated"
    assert result.release_record is not None
    assert result.release_record.decision is GateDecision.PASS
    assert result.parent_target == "variant peptide"
    assert result.emits_parent is False
    assert len(result.provenance.control_decisions) == len(tuple(ControlRole))
    assert result.support_decision.status.value == "supported"
    assert result.result_id.startswith("gate.m2308.")
    assert M2308EvidenceGateEngine().replay(result) == result


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
    result = adjudicate_variant_peptide_evidence_gate(candidate)

    assert result.release_record is not None
    assert result.release_record.decision is decision
    assert any(item.code is finding for item in result.findings)
    assert result.support_decision.status.value == "supported"
    assert result.human_review_required is True


def test_authorization_fails_closed_before_gate_material_is_read() -> None:
    request = _request()
    denied = request.context.model_copy(update={"references": _denied_controls()})
    denied_request = request.model_copy(update={"context": denied})

    with pytest.raises(M2308AuthorizationError):
        M2308EvidenceGateEngine().adjudicate(denied_request)
    with pytest.raises(M2308AuthorizationError):
        M2308EvidenceGateEngine().adjudicate({"context": {"references": {}}})


def test_service_accepts_mapping_and_strict_canonical_json() -> None:
    service = M2308Service()
    request = _request()
    encoded = canonical_json_bytes(request.model_dump(mode="json"))

    from_mapping = service.adjudicate(request.model_dump(mode="json"))
    from_json = service.adjudicate(encoded)

    assert from_mapping == from_json
    assert service.replay(from_json.model_dump(mode="json")) == from_json
    assert service.descriptor["module_id"] == "GLIO-PROTEOGEN-M23-08"
    assert service.descriptor["unsupported_to_negative"] is False


def test_plugin_requires_capability_token_and_supports_string_submission() -> None:
    plugin = M2308Plugin()
    request = _request()
    payload = canonical_json_bytes(request.model_dump(mode="json"))
    token = plugin.validate(EvidenceGateSubmission(payload))
    result = plugin.run(token)

    assert result.request.request_id == request.request_id
    assert plugin.replay(result.model_dump(mode="json")) == result
    with pytest.raises(M2308TokenError):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_rejects_forged_and_cross_instance_tokens() -> None:
    plugin = M2308Plugin()
    other_plugin = M2308Plugin()
    token = plugin.validate(EvidenceGateSubmission(_request()))
    forged = ValidatedM2308Request(token.request, object())

    with pytest.raises(M2308TokenError):
        plugin.run(forged)
    with pytest.raises(M2308TokenError):
        other_plugin.run(token)


def test_plugin_rejects_nested_request_mutation_after_validation() -> None:
    plugin = M2308Plugin()
    token = plugin.validate(EvidenceGateSubmission(_request()))
    changed_requirement = token.request.requirements[0].model_copy(
        update={"statement": "forged nested requirement"}
    )
    object.__setattr__(
        token.request,
        "requirements",
        (changed_requirement, *token.request.requirements[1:]),
    )

    with pytest.raises(M2308TokenError):
        plugin.run(token)


def test_replay_rejects_tampered_result_and_tampered_request() -> None:
    result = M2308EvidenceGateEngine().adjudicate(_request())
    tampered_result = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    tampered_request = result.request.model_copy(update={"request_id": "m2308.request.tampered"})
    tampered_request_result = result.model_copy(update={"request": tampered_request})

    with pytest.raises(M2308ReplayError):
        M2308EvidenceGateEngine().replay(tampered_result)
    with pytest.raises(M2308ReplayError):
        M2308EvidenceGateEngine().replay(tampered_request_result)


def test_descriptor_declares_boundaries_without_claim_inflation() -> None:
    descriptor = M2308Plugin().descriptor

    assert descriptor.parent_target == "variant peptide"
    assert descriptor.provisional_abi is True
    assert descriptor.traceability is True
    assert descriptor.risk_controls is True
    assert descriptor.unsupported_to_negative is False
    assert descriptor.kinase_activity is False
    assert descriptor.all_omics_fusion is False
    assert descriptor.treatment_recommendation is False
    assert descriptor.identity_inference is False
    assert descriptor.consent_inference is False

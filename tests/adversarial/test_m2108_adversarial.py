"""Adversarial contract and replay closure for M21-08."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m21_08 import (
    M2108_DOSSIER_SHA256,
    M2108_DOSSIER_SLICE,
    M2108_M2106_INPUT_MEDIA_TYPE,
    M2108_M2107_INPUT_MEDIA_TYPE,
    M2108_MODULE_ID,
    AdjudicateComplexActivityEvidenceGateRequest,
    ApprovalDecision,
    ApprovalRecord,
    BenchmarkOutcome,
    ComplexActivityEvidenceGateResult,
    GateConfiguration,
    GateDecision,
    GateFinding,
    GateFindingCode,
    GateRequirement,
    GateRunStatus,
    PostReleaseObligation,
    RequirementCategory,
    ResidualRisk,
    RiskSeverity,
    SignedReleaseRecord,
    canonical_request_digest,
    contract_json_schemas,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c21_reference_material.m21_08_evidence_gate_release_adjudicator import (
    M2108Engine,
    M2108ReplayError,
)

_SCHEMA_COUNT = 9


def _metadata(schema: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", schema["x-glio-contract"])


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2108.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2108:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(name: str, media_type: str = "application/json") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name, media_type),
        role="evidence",
        claim="Caller-declared M21-08 release evidence.",
    )


def _context(request_id: str = "request.m2108.synthetic") -> ExecutionContext:
    artifact = _artifact("control")
    accepted = UpstreamDecisionReference(
        decision_id="decision.m2108.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m2108.synthetic",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2108.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2108.identity"),
                evidence=artifact,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.m2108.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _requirement(index: int = 1, *, satisfied: bool = True) -> GateRequirement:
    return GateRequirement(
        requirement_id=f"requirement.m2108.{index}",
        category=RequirementCategory.TRACEABILITY,
        statement="Traceability evidence is complete and reproducible.",
        satisfied=satisfied,
        evidence=(_evidence(f"requirement-{index}"),),
    )


def _benchmark(index: int = 1, *, passed: bool = True) -> BenchmarkOutcome:
    return BenchmarkOutcome(
        benchmark_id=f"benchmark.m2108.{index}",
        name="locked evidence gate benchmark",
        metric_name="p95_latency_ns",
        observed_value=200.0 if passed else 100.0,
        required_floor=150.0,
        passed=passed,
        report_artifact=_artifact(f"benchmark-report-{index}"),
        evidence=(_evidence(f"benchmark-{index}"),),
    )


def _risk(index: int = 1, *, critical: bool = False, accepted: bool = True) -> ResidualRisk:
    return ResidualRisk(
        risk_id=f"risk.m2108.{index}",
        severity=RiskSeverity.CRITICAL if critical else RiskSeverity.ROUTINE,
        statement="Owner review remains required for provisional release metadata.",
        mitigation="Retain abstention and owner approval before promotion.",
        accepted=accepted,
        evidence=(_evidence(f"risk-{index}"),),
    )


def _approval(
    index: int = 1, decision: ApprovalDecision = ApprovalDecision.APPROVE
) -> ApprovalRecord:
    return ApprovalRecord(
        approval_id=f"approval.m2108.{index}",
        approver_token=f"approver.m2108.{index}",
        role="release reviewer",
        decision=decision,
        signature_digest=sha256_digest(f"signature-{index}"),
        evidence=(_evidence(f"approval-{index}"),),
    )


def _obligation(index: int = 1) -> PostReleaseObligation:
    return PostReleaseObligation(
        obligation_id=f"obligation.m2108.{index}",
        owner="ML engineering",
        trigger="owner ABI review",
        action="re-run the evidence gate before promotion",
        evidence=(_evidence(f"obligation-{index}"),),
    )


def _configuration() -> GateConfiguration:
    return GateConfiguration(
        configuration_id="configuration.m2108.synthetic",
        version="1.0.0",
        evidence=(_evidence("configuration"),),
    )


def _request() -> AdjudicateComplexActivityEvidenceGateRequest:
    m2107 = _artifact("m2107-upstream", M2108_M2107_INPUT_MEDIA_TYPE)
    m2106 = _artifact("m2106-robustness", M2108_M2106_INPUT_MEDIA_TYPE)
    return AdjudicateComplexActivityEvidenceGateRequest(
        request_id="request.m2108.synthetic",
        context=_context(),
        upstream_evidence=m2107,
        requirements=(_requirement(),),
        benchmarks=(_benchmark(),),
        residual_risks=(_risk(),),
        approvals=(_approval(),),
        post_release_obligations=(_obligation(),),
        configuration=_configuration(),
        source_artifacts=(m2107, m2106),
    )


def _release_record(request: AdjudicateComplexActivityEvidenceGateRequest) -> SignedReleaseRecord:
    del request
    return SignedReleaseRecord(
        release_id="release.m2108.synthetic",
        version="1.0.0",
        decision=GateDecision.PASS,
        requirements=(_requirement(),),
        benchmarks=(_benchmark(),),
        residual_risks=(_risk(),),
        approvals=(_approval(),),
        post_release_obligations=(_obligation(),),
        limitations=("Provisional ABI requires owner confirmation.",),
        signature_digest=sha256_digest("release-signature"),
        evidence=(_evidence("release-record"),),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="This gate does not estimate scientific model uncertainty.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Release status is sensitive to evidence completeness and approval.",),
    )


def _provenance(request: AdjudicateComplexActivityEvidenceGateRequest) -> ProvenanceRecord:
    refs = request.context.references
    control_decisions = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id="activity.m2108.synthetic",
        actor_id=request.context.actor_id,
        module_id=M2108_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=tuple(item.digest for item in request.source_artifacts),
        configuration_digest=request.configuration.evidence[0].reference.digest,
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=request.context.references.consent.state,
        consent_policy_version=request.context.references.consent.policy_version,
        consent_evidence_digest=request.context.references.consent.evidence.digest,
        control_decisions=control_decisions,
    )


def _result(
    request: AdjudicateComplexActivityEvidenceGateRequest,
) -> ComplexActivityEvidenceGateResult:
    payload: dict[str, Any] = {
        "output_type": "complex_activity_evidence_gate",
        "result_id": f"result.{canonical_request_digest(request).removeprefix('sha256:')}",
        "result_version": "0.1.0-provisional",
        "request_digest": canonical_request_digest(request),
        "result_digest": "sha256:" + "0" * 64,
        "request": request,
        "status": GateRunStatus.ADJUDICATED,
        "release_record": _release_record(request),
        "findings": (),
        "abstention_reason": None,
        "parent_target": "complex activity",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="gate_passed",
            rationale="All declared release controls are satisfied.",
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request),
        "evidence": (_evidence("result-upstream"), _evidence("result-release")),
        "limitations": (
            Limitation(code="provisional", statement="Owner review remains required."),
        ),
        "human_review_required": True,
    }
    candidate = ComplexActivityEvidenceGateResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(candidate)
    return ComplexActivityEvidenceGateResult(**payload)


def _self_rehashed(
    result: ComplexActivityEvidenceGateResult,
    updates: dict[str, Any],
) -> ComplexActivityEvidenceGateResult:
    forged = result.model_copy(update=updates)
    return type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
    )


def test_schema_metadata_locks_authority_and_media_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    for schema in schemas.values():
        metadata = _metadata(schema)
        assert metadata["dossierSha256"] == M2108_DOSSIER_SHA256
        assert metadata["dossierSlice"] == M2108_DOSSIER_SLICE
        assert metadata["m2107InputMediaType"] == M2108_M2107_INPUT_MEDIA_TYPE
        assert metadata["m2106InputMediaType"] == M2108_M2106_INPUT_MEDIA_TYPE
        assert metadata["unsupportedToNegative"] is False


def test_request_requires_context_upstream_and_both_source_media_types() -> None:
    request = _request()
    wrong = request.model_dump(mode="python")
    wrong["upstream_evidence"]["media_type"] = "application/json"
    with pytest.raises(ValidationError, match="M21-07"):
        AdjudicateComplexActivityEvidenceGateRequest(**wrong)

    missing_m2106 = request.model_dump(mode="python")
    missing_m2106["source_artifacts"] = (missing_m2106["source_artifacts"][0],)
    with pytest.raises(ValidationError, match="M21-06"):
        AdjudicateComplexActivityEvidenceGateRequest(**missing_m2106)

    mismatched_context = request.model_dump(mode="python")
    mismatched_context["context"]["request_id"] = "request.other"
    with pytest.raises(ValidationError, match="request identifier"):
        AdjudicateComplexActivityEvidenceGateRequest(**mismatched_context)


def test_numeric_benchmark_and_passed_gate_floor_are_closed() -> None:
    with pytest.raises(ValidationError):
        BenchmarkOutcome(
            **(_benchmark().model_dump(mode="python") | {"observed_value": float("nan")})
        )
    with pytest.raises(ValidationError, match="required floor"):
        BenchmarkOutcome(**_benchmark().model_dump(mode="python") | {"observed_value": 1.0})
    failed = _release_record(_request()).model_dump(mode="python")
    failed["requirements"] = (_requirement(satisfied=False),)
    with pytest.raises(ValidationError, match="unsatisfied"):
        SignedReleaseRecord(**failed)


def test_release_record_rejects_open_critical_risk_and_nonapproval() -> None:
    base = _release_record(_request()).model_dump(mode="python")
    base["residual_risks"] = (_risk(critical=True, accepted=False),)
    with pytest.raises(ValidationError, match="open critical"):
        SignedReleaseRecord(**base)
    base["residual_risks"] = (_risk(),)
    base["approvals"] = (_approval(decision=ApprovalDecision.DEFER),)
    with pytest.raises(ValidationError, match="approval records"):
        SignedReleaseRecord(**base)


def test_release_record_and_result_identifiers_evidence_and_replay_are_closed() -> None:
    request = _request()
    result = _result(request)
    assert result.result_digest == result_payload_digest(result)
    assert result.request_digest == canonical_request_digest(request)

    tampered = result.model_dump(mode="python")
    tampered["result_id"] = "result.tampered"
    with pytest.raises(ValidationError, match="result identifier"):
        ComplexActivityEvidenceGateResult(**tampered)

    duplicate = result.model_dump(mode="python")
    duplicate["evidence"] = (duplicate["evidence"][0],) * 2
    with pytest.raises(ValidationError, match="evidence"):
        ComplexActivityEvidenceGateResult(**duplicate)

    record = _release_record(request).model_dump(mode="python")
    record["requirements"] = (_requirement(), _requirement())
    with pytest.raises(ValidationError, match="identifiers"):
        SignedReleaseRecord(**record)


@pytest.mark.parametrize(
    "region",
    ["release_record", "support_decision", "provenance", "evidence", "limitations"],
)
def test_self_rehashed_release_evidence_regions_are_rejected_by_replay(region: str) -> None:
    result = _result(_request())
    if region == "release_record":
        assert result.release_record is not None
        updates: dict[str, Any] = {
            "release_record": result.release_record.model_copy(
                update={"signature_digest": sha256_digest("forged-release")}
            )
        }
    elif region == "support_decision":
        updates = {
            "support_decision": result.support_decision.model_copy(
                update={"rationale": "Forged release approval."}
            )
        }
    elif region == "provenance":
        updates = {"provenance": result.provenance.model_copy(update={"actor_id": "actor.forged"})}
    elif region == "evidence":
        evidence = result.evidence[0].model_copy(update={"claim": "Forged evidence claim."})
        updates = {"evidence": (evidence, *result.evidence[1:])}
    else:
        updates = {
            "limitations": (
                result.limitations[0].model_copy(update={"statement": "Forged limitation."}),
                *result.limitations[1:],
            )
        }
    forged = _self_rehashed(result, updates)
    assert forged.result_digest == result_payload_digest(forged)
    with pytest.raises(M2108ReplayError, match="replay"):
        M2108Engine().verify(forged)


def test_self_rehashed_request_and_disabled_replay_are_rejected() -> None:
    request = _request()
    result = _result(request)
    changed_request = request.model_copy(update={"request_id": "request.m2108.forged"})
    forged = _self_rehashed(result, {"request": changed_request})
    with pytest.raises(M2108ReplayError, match="result is invalid"):
        M2108Engine().verify(forged)
    with pytest.raises(ValueError, match="cannot be disabled"):
        M2108Engine().verify(result, replay=False)


def test_abstained_result_requires_safe_status_and_no_release_record() -> None:
    request = _request()
    base = _result(request).model_dump(mode="python")
    base["status"] = GateRunStatus.ABSTAINED
    base["release_record"] = None
    base["abstention_reason"] = "Critical evidence remains unresolved."
    base["support_decision"] = SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="critical_risk_open",
        rationale="External owner review is required.",
    )
    base["human_review_required"] = True
    base.pop("result_digest")
    candidate = ComplexActivityEvidenceGateResult.model_construct(
        **base,
        result_digest="sha256:" + "0" * 64,
    )
    base["result_digest"] = result_payload_digest(candidate)
    abstained = ComplexActivityEvidenceGateResult(**base)
    assert abstained.status is GateRunStatus.ABSTAINED
    assert abstained.release_record is None


def test_strict_models_reject_duplicate_findings_and_extra_fields() -> None:
    result = _result(_request())
    finding = GateFinding(
        finding_id="finding.m2108.duplicate",
        code=GateFindingCode.REQUIREMENT_UNSATISFIED,
        message="Requirement needs review.",
    )
    payload = result.model_dump(mode="python")
    payload["findings"] = (finding, finding)
    with pytest.raises(ValidationError, match="finding ids"):
        ComplexActivityEvidenceGateResult(**payload)
    requirement = _requirement().model_dump(mode="python")
    requirement["unexpected"] = True
    with pytest.raises(ValidationError, match="unexpected"):
        GateRequirement(**requirement)

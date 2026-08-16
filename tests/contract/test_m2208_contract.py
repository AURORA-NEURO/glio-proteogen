"""Adversarial contract and replay tests for provisional M22-08."""

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m22_08 import (
    M2208_OUTPUT_MEDIA_TYPE,
    M2208_PROVISIONAL_ABI,
    AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
    ApprovalDecision,
    ApprovalRecord,
    BenchmarkOutcome,
    GateConfiguration,
    GateDecision,
    GateFinding,
    GateFindingCode,
    GateRequirement,
    GateRunStatus,
    PostReleaseObligation,
    ProteinRnaDiscordanceEvidenceGateResult,
    RequirementCategory,
    ResidualRisk,
    RiskSeverity,
    SignedReleaseRecord,
    canonical_request_digest,
    contract_json_schemas,
    result_identifier,
    result_payload_digest,
)
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

_SCHEMA_COUNT = 10
_VERSION = "0.1.0"
_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def _digest(seed: str) -> str:
    return "sha256:" + sha256(seed.encode("utf-8")).hexdigest()


def _metadata(schema: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", schema["x-glio-contract"])


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version=_VERSION,
        digest=_digest(name),
        media_type="application/json",
    )


def _evidence(name: str = "evidence") -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Caller-declared gate evidence.",
    )


def _context(request_id: str) -> ExecutionContext:
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor-m2208",
        occurred_at=_NOW,
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="config-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=_VERSION,
                evidence=_artifact("configuration-evidence"),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="identity-decision",
                state=IdentityLineageState.RESOLVED,
                policy_version=_VERSION,
                binding_digest=_digest("identity-binding"),
                evidence=_artifact("identity-evidence"),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="provenance-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=_VERSION,
                evidence=_artifact("provenance-evidence"),
            ),
            consent=ConsentReference(
                decision_id="consent-decision",
                state=ConsentState.GRANTED,
                policy_version=_VERSION,
                evidence=_artifact("consent-evidence"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="quality-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=_VERSION,
                evidence=_artifact("quality-evidence"),
            ),
            support=UpstreamDecisionReference(
                decision_id="support-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=_VERSION,
                evidence=_artifact("support-evidence"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="intended-use-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=_VERSION,
                evidence=_artifact("intended-use-evidence"),
            ),
        ),
    )


def _requirements() -> tuple[GateRequirement, ...]:
    return tuple(
        GateRequirement(
            requirement_id=f"requirement-{category.value}",
            category=category,
            statement=f"{category.value} evidence is locked.",
            satisfied=True,
            evidence=(_evidence(f"requirement-{category.value}"),),
        )
        for category in RequirementCategory
    )


def _benchmarks() -> tuple[BenchmarkOutcome, ...]:
    return (
        BenchmarkOutcome(
            benchmark_id="benchmark-release",
            name="release-evaluator",
            metric_name="pass_rate",
            observed_value=1.0,
            required_floor=0.95,
            passed=True,
            report_artifact=_artifact("benchmark-report"),
            evidence=(_evidence("benchmark-evidence"),),
        ),
    )


def _risks() -> tuple[ResidualRisk, ...]:
    return (
        ResidualRisk(
            risk_id="risk-review-only",
            severity=RiskSeverity.ROUTINE,
            statement="Use remains research and development only.",
            mitigation="Require human review for release exceptions.",
            accepted=False,
            evidence=(_evidence("risk-evidence"),),
        ),
    )


def _approvals() -> tuple[ApprovalRecord, ...]:
    return (
        ApprovalRecord(
            approval_id="approval-quality",
            approver_token="quality-reviewer",  # noqa: S106
            role="Quality engineering",
            decision=ApprovalDecision.APPROVE,
            signature_digest=_digest("quality-signature"),
            evidence=(_evidence("approval-evidence"),),
        ),
    )


def _obligations() -> tuple[PostReleaseObligation, ...]:
    return (
        PostReleaseObligation(
            obligation_id="obligation-monitor",
            owner="Quality engineering",
            trigger="new evidence or support boundary",
            action="reopen the gate and record review",
            evidence=(_evidence("obligation-evidence"),),
        ),
    )


def _request() -> AdjudicateProteinRnaDiscordanceEvidenceGateRequest:
    proteome = _artifact("mass-spectrometry-proteome")
    genome = _artifact("genome-transcriptome")
    ptm = _artifact("ptm-annotations")
    upstream = _artifact("m2207-upstream-evidence")
    return AdjudicateProteinRnaDiscordanceEvidenceGateRequest(
        request_id="request-m2208",
        context=_context("request-m2208"),
        mass_spectrometry_proteome=proteome,
        genome_transcriptome=genome,
        ptm_annotations=ptm,
        upstream_evidence=upstream,
        requirements=_requirements(),
        benchmarks=_benchmarks(),
        residual_risks=_risks(),
        approvals=_approvals(),
        post_release_obligations=_obligations(),
        configuration=GateConfiguration(
            configuration_id="configuration-m2208",
            version=_VERSION,
            evidence=(_evidence("configuration-record"),),
        ),
        source_artifacts=(proteome, genome, ptm, upstream),
    )


def _release_record(
    request: AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
) -> SignedReleaseRecord:
    return SignedReleaseRecord(
        release_id="release-m2208",
        version=_VERSION,
        decision=GateDecision.PASS,
        requirements=request.requirements,
        benchmarks=request.benchmarks,
        residual_risks=request.residual_risks,
        approvals=request.approvals,
        post_release_obligations=request.post_release_obligations,
        limitations=("Research and development use only.",),
        signature_digest=_digest("release-signature"),
        evidence=(_evidence("release-evidence"),),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Evidence gate does not estimate this dimension.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
    )


def _provenance() -> ProvenanceRecord:
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=f"control-{role.value}",
            state=(
                "granted"
                if role is ControlRole.CONSENT
                else "resolved"
                if role is ControlRole.IDENTITY_LINEAGE
                else "accepted"
            ),
            policy_version=_VERSION,
            evidence_digest=_digest(f"control-{role.value}"),
            subject_digest=_digest("identity-subject")
            if role is ControlRole.IDENTITY_LINEAGE
            else None,
        )
        for role in ControlRole
    )
    return ProvenanceRecord(
        activity_id="activity-m2208",
        actor_id="actor-m2208",
        module_id="GLIO-PROTEOGEN-M22-08",
        module_version=_VERSION,
        generated_at=_NOW,
        input_digests=(_digest("mass-spectrometry-proteome"),),
        configuration_digest=_digest("configuration-m2208"),
        consent_decision_id="consent-decision",
        consent_state=ConsentState.GRANTED,
        consent_policy_version=_VERSION,
        consent_evidence_digest=_digest("consent-evidence"),
        control_decisions=decisions,
    )


def _result(  # noqa: PLR0913
    request: AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
    *,
    status: GateRunStatus,
    support_status: SupportStatus,
    release_record: SignedReleaseRecord | None,
    findings: tuple[GateFinding, ...] = (),
    abstention_reason: str | None = None,
) -> ProteinRnaDiscordanceEvidenceGateResult:
    request_digest = canonical_request_digest(request)
    payload: dict[str, Any] = {
        "result_id": result_identifier(request_digest),
        "result_version": "0.1.0-provisional",
        "request_digest": request_digest,
        "request": request,
        "status": status,
        "release_record": release_record,
        "findings": findings,
        "abstention_reason": abstention_reason,
        "support_decision": SupportDecision(
            status=support_status,
            reason_code="gate-evidence-supported",
            rationale="Caller-declared evidence gate material is structurally complete.",
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(),
        "evidence": (_evidence("result-evidence"),),
        "limitations": (
            Limitation(
                code="research-only",
                statement="Research and development use only.",
            ),
        ),
    }
    candidate = ProteinRnaDiscordanceEvidenceGateResult.model_construct(
        result_digest=_digest("placeholder-result"),
        **payload,
    )
    return ProteinRnaDiscordanceEvidenceGateResult(
        result_digest=result_payload_digest(candidate),
        **payload,
    )


def test_provisional_schemas_preserve_gate_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(
        cast("str", schema["$schema"]).endswith("2020-12/schema") for schema in schemas.values()
    )
    assert all(_metadata(schema)["provisionalAbi"] for schema in schemas.values())
    assert all(_metadata(schema)["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        _metadata(schema)["traceabilityRequired"]
        and _metadata(schema)["qualityControlsRequired"]
        and _metadata(schema)["riskControlsRequired"]
        and _metadata(schema)["benchmarkOutcomesRequired"]
        and _metadata(schema)["claimCeilingRequired"]
        and _metadata(schema)["residualRiskRequired"]
        and _metadata(schema)["approvalRequired"]
        and _metadata(schema)["postReleaseObligationsRequired"]
        and _metadata(schema)["signedReleaseRecordRequired"]
        and _metadata(schema)["noUnresolvedCriticalRequirements"]
        and _metadata(schema)["humanReviewRequired"]
        and _metadata(schema)["explicitAbstentionRequired"]
        and _metadata(schema)["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        _metadata(schema)["parentTarget"] == "protein-RNA discordance"
        for schema in schemas.values()
    )
    assert _metadata(schemas["output"])["outputMediaType"] == M2208_OUTPUT_MEDIA_TYPE
    assert M2208_PROVISIONAL_ABI is True


def test_request_and_release_close_all_required_categories() -> None:
    request = _request()
    record = _release_record(request)
    assert {item.category for item in request.requirements} == set(RequirementCategory)
    assert record.requirements == request.requirements
    assert canonical_request_digest(request).startswith("sha256:")


def test_request_rejects_context_identity_mismatch() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["context"] = _context("different-request")
    with pytest.raises(ValidationError, match="request ID"):
        AdjudicateProteinRnaDiscordanceEvidenceGateRequest.model_validate(payload)


def test_request_rejects_missing_declared_source_artifact() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = request.source_artifacts[:-1]
    with pytest.raises(ValidationError, match="source artifacts"):
        AdjudicateProteinRnaDiscordanceEvidenceGateRequest.model_validate(payload)


def test_request_rejects_incomplete_requirement_categories() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["requirements"] = request.requirements[:-1]
    with pytest.raises(ValidationError, match="required requirement category"):
        AdjudicateProteinRnaDiscordanceEvidenceGateRequest.model_validate(payload)


def test_benchmark_rejects_nonfinite_and_inconsistent_pass() -> None:
    with pytest.raises(ValidationError):
        BenchmarkOutcome(
            benchmark_id="benchmark-nan",
            name="invalid",
            metric_name="score",
            observed_value=float("nan"),
            required_floor=0.5,
            passed=False,
            report_artifact=_artifact("benchmark-nan-report"),
            evidence=(_evidence("benchmark-nan-evidence"),),
        )
    with pytest.raises(ValidationError, match="passed flag"):
        BenchmarkOutcome(
            benchmark_id="benchmark-mismatch",
            name="invalid",
            metric_name="score",
            observed_value=0.1,
            required_floor=0.5,
            passed=True,
            report_artifact=_artifact("benchmark-mismatch-report"),
            evidence=(_evidence("benchmark-mismatch-evidence"),),
        )


def test_result_replay_identity_and_abstention_are_closed() -> None:
    request = _request()
    result = _result(
        request,
        status=GateRunStatus.ADJUDICATED,
        support_status=SupportStatus.SUPPORTED,
        release_record=_release_record(request),
    )
    assert result.result_digest == result_payload_digest(result)
    tampered = result.model_dump(mode="python")
    tampered["result_id"] = "adjudication.m2208." + "0" * 64
    with pytest.raises(ValidationError, match="identifier"):
        ProteinRnaDiscordanceEvidenceGateResult.model_validate(tampered)

    abstained = _result(
        request,
        status=GateRunStatus.ABSTAINED,
        support_status=SupportStatus.REVIEW_REQUIRED,
        release_record=None,
        findings=(
            GateFinding(
                finding_id="finding-review",
                code=GateFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="Owner confirmation is required.",
            ),
        ),
        abstention_reason="provisional ABI requires human review",
    )
    assert abstained.release_record is None


def test_abstention_requires_safe_finding_and_status() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="at least one finding"):
        _result(
            request,
            status=GateRunStatus.ABSTAINED,
            support_status=SupportStatus.UNSUPPORTED,
            release_record=None,
            abstention_reason="missing owner confirmation",
        )

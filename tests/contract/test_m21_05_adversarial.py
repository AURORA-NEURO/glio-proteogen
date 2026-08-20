"""Adversarial contract and replay closure for M21-05."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m21_05 import (
    M2105_CONTRACT_VERSION,
    M2105_M2104_INPUT_MEDIA_TYPE,
    M2105_MODULE_ID,
    CalibrationSummary,
    ComplexActivitySubgroupEvaluationResult,
    CoverageStatus,
    CoverageSummary,
    EquityStatus,
    EvaluateComplexActivitySubgroupEquityRequest,
    EvaluationConfiguration,
    EvaluationStatus,
    SubgroupDimension,
    SubgroupEvaluationReport,
    SubgroupFinding,
    SubgroupFindingCode,
    SubgroupPerformance,
    canonical_request_digest,
    normalized_request,
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


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2105.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2105:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M21-05 subgroup evaluation evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2105.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context(request_id: str = "request.m2105.synthetic") -> ExecutionContext:
    artifacts = {
        role: _artifact(role)
        for role in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "consent",
            "intended_use",
        )
    }
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m2105.synthetic",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2105.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2105.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m2105.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _performance(dimension: SubgroupDimension, subgroup: str | None = None) -> SubgroupPerformance:
    name = subgroup or f"{dimension.value}.synthetic"
    return SubgroupPerformance(
        metric_id=f"metric.m2105.{dimension.value}",
        dimension=dimension,
        subgroup=name,
        sample_size=10,
        metric_name="balanced_accuracy",
        value=0.8,
        lower_bound=0.7,
        upper_bound=0.9,
        safety_floor=0.5,
        coverage_status=CoverageStatus.ADEQUATE,
        equity_status=EquityStatus.WITHIN_FLOOR,
        evidence=(_evidence(_artifact(f"metric-{dimension.value}")),),
    )


def _calibration(dimension: SubgroupDimension, subgroup: str | None = None) -> CalibrationSummary:
    name = subgroup or f"{dimension.value}.synthetic"
    return CalibrationSummary(
        calibration_id=f"calibration.m2105.{dimension.value}",
        dimension=dimension,
        subgroup=name,
        expected_calibration_error=0.1,
        nominal_coverage=0.9,
        coverage_target=0.9,
        status=EvaluationStatus.EVALUATED,
        evidence=(_evidence(_artifact(f"calibration-{dimension.value}")),),
    )


def _coverage(dimension: SubgroupDimension, subgroup: str | None = None) -> CoverageSummary:
    name = subgroup or f"{dimension.value}.synthetic"
    return CoverageSummary(
        coverage_id=f"coverage.m2105.{dimension.value}",
        dimension=dimension,
        subgroup=name,
        supported_examples=8,
        total_examples=10,
        coverage_fraction=0.8,
        status=CoverageStatus.ADEQUATE,
        evidence=(_evidence(_artifact(f"coverage-{dimension.value}")),),
    )


def _configuration() -> EvaluationConfiguration:
    return EvaluationConfiguration(
        configuration_id="configuration.m2105.synthetic",
        version="1.0.0",
        nominal_coverage_target=0.9,
        safety_floor=0.5,
        required_dimensions=tuple(SubgroupDimension),
        evidence=(_evidence(_artifact("configuration-evaluation")),),
    )


def _request() -> EvaluateComplexActivitySubgroupEquityRequest:
    upstream = _artifact("upstream", M2105_M2104_INPUT_MEDIA_TYPE)
    dimensions = tuple(SubgroupDimension)
    return EvaluateComplexActivitySubgroupEquityRequest(
        request_id="request.m2105.synthetic",
        context=_context(),
        upstream_result=upstream,
        performance=tuple(_performance(dimension) for dimension in dimensions),
        calibration=tuple(_calibration(dimension) for dimension in dimensions),
        coverage=tuple(_coverage(dimension) for dimension in dimensions),
        configuration=_configuration(),
        source_artifacts=(upstream,),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M21-05 evaluates declared subgroup evidence and does not infer biology.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=("Equity evaluation is sensitive to subgroup support and calibration.",),
    )


def _provenance(request: EvaluateComplexActivitySubgroupEquityRequest) -> ProvenanceRecord:
    refs = request.context.references
    records = (
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
        activity_id="activity.m2105.synthetic",
        actor_id=request.context.actor_id,
        module_id=M2105_MODULE_ID,
        module_version=M2105_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            canonical_request_digest(request),
            request.upstream_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
        ),
        configuration_digest=request.configuration.evidence[0].reference.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=records,
    )


def _report(request: EvaluateComplexActivitySubgroupEquityRequest) -> SubgroupEvaluationReport:
    evidence = (_evidence(request.upstream_result),)
    return SubgroupEvaluationReport(
        report_id="report.m2105.synthetic",
        version="1.0.0",
        performance=request.performance,
        calibration=request.calibration,
        coverage=request.coverage,
        configuration=request.configuration,
        evidence=evidence,
    )


def _result() -> ComplexActivitySubgroupEvaluationResult:
    request = _request()
    evidence = (_evidence(request.upstream_result),)
    payload: dict[str, Any] = {
        "output_type": "complex_activity_subgroup_evaluation",
        "result_id": f"result.{canonical_request_digest(request).removeprefix('sha256:')}",
        "result_version": "0.1.0-provisional",
        "request_digest": canonical_request_digest(request),
        "result_digest": "sha256:" + "0" * 64,
        "request": request,
        "status": EvaluationStatus.EVALUATED,
        "report": _report(request),
        "findings": (),
        "abstention_reason": None,
        "parent_target": "complex activity",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="synthetic_supported",
            rationale="Caller-declared subgroup evidence is supported.",
        ),
        "uncertainty": _uncertainty(),
        "provenance": _provenance(request),
        "evidence": evidence,
        "limitations": (
            Limitation(code="provisional", statement="ABI remains provisional pending review."),
        ),
        "human_review_required": False,
    }
    constructed = ComplexActivitySubgroupEvaluationResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(constructed)
    return TypeAdapter(ComplexActivitySubgroupEvaluationResult).validate_python(
        payload, strict=True
    )


def test_numeric_fields_are_finite_and_bounds_are_closed() -> None:
    performance = _performance(SubgroupDimension.AGE)
    with pytest.raises(ValidationError):
        SubgroupPerformance.model_validate(performance.model_dump() | {"value": float("nan")})
    with pytest.raises(ValidationError, match="bounds"):
        SubgroupPerformance.model_validate(
            performance.model_dump() | {"lower_bound": 0.95, "upper_bound": 0.9}
        )
    with pytest.raises(ValidationError, match="within bounds"):
        SubgroupPerformance.model_validate(performance.model_dump() | {"value": 0.95})
    with pytest.raises(ValidationError, match="below-floor"):
        SubgroupPerformance.model_validate(
            performance.model_dump()
            | {
                "value": 0.6,
                "lower_bound": 0.5,
                "upper_bound": 0.7,
                "equity_status": EquityStatus.BELOW_FLOOR,
            }
        )
    coverage = _coverage(SubgroupDimension.AGE)
    with pytest.raises(ValidationError, match="fraction"):
        CoverageSummary.model_validate(coverage.model_dump() | {"coverage_fraction": 0.7})
    with pytest.raises(ValidationError, match="exceed"):
        CoverageSummary.model_validate(
            coverage.model_dump() | {"supported_examples": 11, "coverage_fraction": 1.0}
        )


def test_canonical_projection_accepts_mapping_inputs() -> None:
    assert normalized_request({"module": "M21-05"}) == {"module": "M21-05"}


def test_configuration_requires_all_eight_dimensions_exactly() -> None:
    configuration = _configuration()
    with pytest.raises(ValidationError, match="at least 8"):
        EvaluationConfiguration.model_validate(
            configuration.model_dump() | {"required_dimensions": tuple(SubgroupDimension)[:-1]}
        )
    with pytest.raises(ValidationError, match="all subgroup dimensions"):
        EvaluationConfiguration.model_validate(
            configuration.model_dump()
            | {"required_dimensions": (*tuple(SubgroupDimension)[:-1], SubgroupDimension.AGE)}
        )


def test_report_requires_performance_calibration_coverage_alignment() -> None:
    request = _request()
    report = _report(request)
    with pytest.raises(ValidationError, match="align"):
        SubgroupEvaluationReport.model_validate(
            report.model_dump() | {"coverage": report.coverage[:-1]}
        )
    duplicate = report.model_dump()
    duplicate["performance"] = (duplicate["performance"][0],) * 2
    duplicate["calibration"] = (duplicate["calibration"][0],) * 2
    duplicate["coverage"] = (duplicate["coverage"][0],) * 2
    with pytest.raises(ValidationError, match="report ids"):
        SubgroupEvaluationReport.model_validate(duplicate)


def test_request_requires_exact_upstream_media_context_and_source_closure() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="M21-04"):
        EvaluateComplexActivitySubgroupEquityRequest.model_validate(
            request.model_dump()
            | {
                "upstream_result": request.upstream_result.model_copy(
                    update={"media_type": "application/json"}
                )
            }
        )
    with pytest.raises(ValidationError, match="request identifier"):
        EvaluateComplexActivitySubgroupEquityRequest.model_validate(
            request.model_dump()
            | {"context": request.context.model_copy(update={"request_id": "request.other"})}
        )
    with pytest.raises(ValidationError, match="include upstream"):
        EvaluateComplexActivitySubgroupEquityRequest.model_validate(
            request.model_dump() | {"source_artifacts": (_artifact("other"),)}
        )
    with pytest.raises(ValidationError, match="source artifacts"):
        EvaluateComplexActivitySubgroupEquityRequest.model_validate(
            request.model_dump() | {"source_artifacts": (request.upstream_result,) * 2}
        )


def test_result_identity_evidence_finding_and_status_closures() -> None:
    result = _result()
    payload = result.model_dump()
    with pytest.raises(ValidationError, match="result identifier"):
        TypeAdapter(ComplexActivitySubgroupEvaluationResult).validate_python(
            payload | {"result_id": "result.tampered"}, strict=True
        )
    finding = SubgroupFinding(
        finding_id="finding.m2105.duplicate",
        code=SubgroupFindingCode.CALIBRATION_FAILURE,
        message="Calibration requires review.",
    )
    with pytest.raises(ValidationError, match="finding ids"):
        TypeAdapter(ComplexActivitySubgroupEvaluationResult).validate_python(
            payload | {"findings": (finding, finding)}, strict=True
        )
    with pytest.raises(ValidationError, match="request digest"):
        TypeAdapter(ComplexActivitySubgroupEvaluationResult).validate_python(
            result.model_copy(update={"request_digest": "sha256:" + "f" * 64}), strict=True
        )
    with pytest.raises(ValidationError, match="evidence"):
        TypeAdapter(ComplexActivitySubgroupEvaluationResult).validate_python(
            result.model_copy(update={"evidence": result.evidence * 2}), strict=True
        )
    with pytest.raises(ValidationError, match="evaluated result"):
        TypeAdapter(ComplexActivitySubgroupEvaluationResult).validate_python(
            result.model_copy(update={"report": None}), strict=True
        )
    with pytest.raises(ValidationError, match="abstained result"):
        TypeAdapter(ComplexActivitySubgroupEvaluationResult).validate_python(
            result.model_copy(update={"status": EvaluationStatus.ABSTAINED}), strict=True
        )
    abstained = result.model_copy(
        update={
            "status": EvaluationStatus.ABSTAINED,
            "report": None,
            "abstention_reason": "Support is insufficient.",
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="review_required",
                rationale="Review is required before evaluation.",
            ),
            "human_review_required": True,
        }
    )
    abstained = abstained.model_copy(update={"result_digest": result_payload_digest(abstained)})
    assert (
        TypeAdapter(ComplexActivitySubgroupEvaluationResult)
        .validate_python(abstained, strict=True)
        .status
        is EvaluationStatus.ABSTAINED
    )


def test_result_replay_digest_rejects_payload_tampering() -> None:
    result = _result()
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValidationError, match="result digest"):
        TypeAdapter(ComplexActivitySubgroupEvaluationResult).validate_python(tampered, strict=True)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("module_id", "GLIO-PROTEOGEN-M21-04"),
        ("module_version", "9.9.9"),
        ("configuration_digest", "sha256:" + "f" * 64),
        ("input_digests", ("sha256:" + "f" * 64,)),
    ],
)
def test_result_rejects_self_rehashed_provenance_binding_forgery(
    field: str,
    value: object,
) -> None:
    result = _result()
    forged = result.model_copy(
        update={"provenance": result.provenance.model_copy(update={field: value})}
    )
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    with pytest.raises(ValidationError, match="provenance"):
        TypeAdapter(ComplexActivitySubgroupEvaluationResult).validate_python(
            forged, strict=True
        )

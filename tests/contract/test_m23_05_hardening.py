"""Adversarial contract and replay closure for provisional M23-05."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m23_05 import (
    M2305_DOSSIER_SHA256,
    M2305_DOSSIER_SLICE,
    M2305_M2304_INPUT_MEDIA_TYPE,
    M2305_MODULE_ID,
    CalibrationSummary,
    CoverageStatus,
    CoverageSummary,
    EquityStatus,
    EvaluateVariantPeptideSubgroupEquityRequest,
    EvaluationConfiguration,
    EvaluationStatus,
    SubgroupDimension,
    SubgroupEvaluationReport,
    SubgroupFinding,
    SubgroupFindingCode,
    SubgroupPerformance,
    VariantPeptideSubgroupEvaluationResult,
    canonical_request_digest,
    contract_json_schemas,
    result_identifier,
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
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Caller-declared M23-05 subgroup evidence.",
    )


def _context(request_id: str = "request-1") -> ExecutionContext:
    artifact = _artifact("context-artifact")
    accepted = UpstreamDecisionReference(
        decision_id="decision-accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="subgroup-actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="identity-resolved",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=artifact,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="consent-granted",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _performance(dimension: SubgroupDimension) -> SubgroupPerformance:
    return SubgroupPerformance(
        metric_id=f"performance-{dimension.value}",
        dimension=dimension,
        subgroup=f"{dimension.value}-reference",
        sample_size=20,
        metric_name="balanced_accuracy",
        value=0.7,
        lower_bound=0.4,
        upper_bound=0.8,
        safety_floor=0.6,
        coverage_status=CoverageStatus.ADEQUATE,
        equity_status=EquityStatus.WITHIN_FLOOR,
        evidence=(_evidence(f"performance-{dimension.value}-evidence"),),
    )


def _calibration(dimension: SubgroupDimension) -> CalibrationSummary:
    return CalibrationSummary(
        calibration_id=f"calibration-{dimension.value}",
        dimension=dimension,
        subgroup=f"{dimension.value}-reference",
        expected_calibration_error=0.04,
        nominal_coverage=0.9,
        coverage_target=0.9,
        status=EvaluationStatus.EVALUATED,
        evidence=(_evidence(f"calibration-{dimension.value}-evidence"),),
    )


def _coverage(dimension: SubgroupDimension) -> CoverageSummary:
    return CoverageSummary(
        coverage_id=f"coverage-{dimension.value}",
        dimension=dimension,
        subgroup=f"{dimension.value}-reference",
        supported_examples=8,
        total_examples=10,
        coverage_fraction=0.8,
        status=CoverageStatus.ADEQUATE,
        evidence=(_evidence(f"coverage-{dimension.value}-evidence"),),
    )


def _configuration() -> EvaluationConfiguration:
    return EvaluationConfiguration(
        configuration_id="configuration-1",
        version="1.0.0",
        nominal_coverage_target=0.9,
        safety_floor=0.6,
        required_dimensions=tuple(SubgroupDimension),
        evidence=(_evidence("configuration-evidence"),),
    )


def _request() -> EvaluateVariantPeptideSubgroupEquityRequest:
    upstream = _artifact("m2304.evaluator", M2305_M2304_INPUT_MEDIA_TYPE)
    dimensions = tuple(SubgroupDimension)
    return EvaluateVariantPeptideSubgroupEquityRequest(
        request_id="request-1",
        context=_context(),
        upstream_result=upstream,
        performance=tuple(_performance(item) for item in dimensions),
        calibration=tuple(_calibration(item) for item in dimensions),
        coverage=tuple(_coverage(item) for item in dimensions),
        configuration=_configuration(),
        source_artifacts=(upstream, _artifact("subgroup-material")),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Caller did not provide calibrated subgroup uncertainty.",
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


def _provenance(request: EvaluateVariantPeptideSubgroupEquityRequest) -> ProvenanceRecord:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    return ProvenanceRecord(
        activity_id="subgroup-activity",
        actor_id=request.context.actor_id,
        module_id=M2305_MODULE_ID,
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=(request.upstream_result.digest,),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=tuple(
            ControlDecisionRecord(
                role=role,
                decision_id=decision.decision_id,
                state=str(decision.state.value),
                policy_version=decision.policy_version,
                evidence_digest=decision.evidence.digest,
                subject_digest=(
                    decision.binding_digest
                    if isinstance(decision, IdentityLineageReference)
                    else None
                ),
            )
            for role, decision in controls
        ),
    )


def _report(request: EvaluateVariantPeptideSubgroupEquityRequest) -> SubgroupEvaluationReport:
    return SubgroupEvaluationReport(
        report_id="report-1",
        version="1.0.0",
        performance=request.performance,
        calibration=request.calibration,
        coverage=request.coverage,
        configuration=request.configuration,
        evidence=(_evidence("report-evidence"),),
    )


def _completed_result(
    request: EvaluateVariantPeptideSubgroupEquityRequest,
) -> VariantPeptideSubgroupEvaluationResult:
    result = VariantPeptideSubgroupEvaluationResult.model_construct(
        result_id=result_identifier(request),
        request_digest=canonical_request_digest(request),
        result_digest=sha256_digest("placeholder"),
        request=request,
        status=EvaluationStatus.EVALUATED,
        report=_report(request),
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="subgroup_supported",
            rationale="Inputs satisfy the provisional subgroup boundary.",
        ),
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        limitations=(Limitation(code="metadata_only", statement="No parent conclusion."),),
    )
    return VariantPeptideSubgroupEvaluationResult.model_validate(
        result.model_copy(update={"result_digest": result_payload_digest(result)}), strict=True
    )


def _request_update(
    request: EvaluateVariantPeptideSubgroupEquityRequest, **updates: object
) -> EvaluateVariantPeptideSubgroupEquityRequest:
    payload = request.model_dump(mode="python")
    payload.update(updates)
    return EvaluateVariantPeptideSubgroupEquityRequest.model_validate(payload, strict=True)


def _result_update(
    result: VariantPeptideSubgroupEvaluationResult, **updates: object
) -> VariantPeptideSubgroupEvaluationResult:
    payload = result.model_dump(mode="python")
    payload.update(updates)
    return VariantPeptideSubgroupEvaluationResult.model_validate(payload, strict=True)


def test_authority_and_schema_metadata_are_explicit() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert M2305_DOSSIER_SHA256.startswith("sha256:")
    assert M2305_DOSSIER_SLICE.endswith(":8132-8172")
    assert all(
        schema["x-glio-contract"]["authoritySha256"] == M2305_DOSSIER_SHA256
        and schema["x-glio-contract"]["authoritySlice"] == M2305_DOSSIER_SLICE
        for schema in schemas.values()
    )


def test_request_closes_context_media_and_source_artifacts() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="context request id"):
        _request_update(request, context=_context("other-request"))
    with pytest.raises(ValidationError, match="provisional M23-04"):
        _request_update(request, upstream_result=_artifact("wrong", "application/wrong"))
    with pytest.raises(ValidationError, match="exact upstream result identity"):
        _request_update(request, source_artifacts=(_artifact("subgroup-material"),))
    with pytest.raises(ValidationError, match="source artifact ids"):
        _request_update(request, source_artifacts=(request.source_artifacts[0],) * 2)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "0.2.0"),
        ("digest", "sha256:" + "f" * 64),
        ("media_type", "application/vnd.glio-proteogen.m23-04+json; forged"),
    ],
)
def test_source_artifacts_retain_full_upstream_identity(field: str, value: str) -> None:
    request = _request()
    forged = request.source_artifacts[0].model_copy(update={field: value})

    with pytest.raises(ValidationError, match="exact upstream result identity"):
        _request_update(request, source_artifacts=(forged, *request.source_artifacts[1:]))


def test_numeric_and_equity_closures_reject_invalid_material() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="finite"):
        _request_update(
            request,
            performance=(
                _performance(SubgroupDimension.AGE).model_copy(update={"value": math.inf}),
                *request.performance[1:],
            ),
        )
    with pytest.raises(ValidationError, match="bounds"):
        _request_update(
            request,
            performance=(
                _performance(SubgroupDimension.AGE).model_copy(update={"lower_bound": 0.9}),
                *request.performance[1:],
            ),
        )
    with pytest.raises(ValidationError, match="below-floor"):
        _request_update(
            request,
            performance=(
                _performance(SubgroupDimension.AGE).model_copy(
                    update={"equity_status": EquityStatus.BELOW_FLOOR}
                ),
                *request.performance[1:],
            ),
        )
    with pytest.raises(ValidationError, match="coverage fraction"):
        _request_update(
            request,
            coverage=(
                _coverage(SubgroupDimension.AGE).model_copy(update={"coverage_fraction": 0.7}),
                *request.coverage[1:],
            ),
        )


def test_report_and_configuration_id_closures_reject_duplicates() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="all subgroup dimensions"):
        _request_update(
            request,
            configuration=_configuration().model_copy(
                update={
                    "required_dimensions": (*tuple(SubgroupDimension)[:-1], SubgroupDimension.AGE)
                }
            ),
        )
    with pytest.raises(ValidationError, match="report ids"):
        SubgroupEvaluationReport.model_validate(
            _report(request).model_dump(mode="python")
            | {
                "calibration": (
                    _calibration(SubgroupDimension.AGE).model_copy(
                        update={"calibration_id": "performance-age"}
                    ),
                    *request.calibration[1:],
                )
            },
            strict=True,
        )


@pytest.mark.parametrize("section", ["performance", "calibration", "coverage"])
def test_report_dimension_closures_reject_missing_dimension(section: str) -> None:
    request = _request()
    report = _report(request)
    source = getattr(report, section)
    changed = source[0].model_copy(update={"dimension": SubgroupDimension.SEX})
    candidate = report.model_dump(mode="python") | {section: (changed, *source[1:])}
    with pytest.raises(ValidationError, match="cover all configured subgroup dimensions"):
        SubgroupEvaluationReport.model_validate(candidate, strict=True)


def test_result_identity_provenance_and_status_closure() -> None:
    request = _request()
    result = _completed_result(request)
    with pytest.raises(ValidationError, match="result id"):
        _result_update(result, result_id="m2305-result:wrong")
    with pytest.raises(ValidationError, match="module id"):
        _result_update(
            result,
            provenance=result.provenance.model_copy(update={"module_id": "GLIO-PROTEOGEN-M23-06"}),
        )
    with pytest.raises(ValidationError, match="upstream result digest"):
        _result_update(
            result,
            provenance=result.provenance.model_copy(
                update={"input_digests": ("sha256:" + "e" * 64,)}
            ),
        )
    finding = SubgroupFinding(
        finding_id="duplicate",
        code=SubgroupFindingCode.CALIBRATION_FAILURE,
        message="failure",
    )
    with pytest.raises(ValidationError, match="finding ids"):
        _result_update(result, findings=(finding, finding))
    with pytest.raises(ValidationError, match="result digest"):
        _result_update(result, result_digest=sha256_digest("tampered"))


def test_result_canonical_identity_is_stable_and_payload_digest_binds_content() -> None:
    request = _request()
    result = _completed_result(request)
    assert result.result_id == result_identifier(request)
    assert result.request_digest == canonical_request_digest(request)
    assert result.result_digest == result_payload_digest(result)
    changed = _request_update(request, request_id="request-2", context=_context("request-2"))
    assert result_identifier(changed) != result.result_id


__all__ = ["_completed_result", "_request"]

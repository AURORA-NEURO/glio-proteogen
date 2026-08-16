"""Adversarial contract closure for provisional M24-05."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m24_05 import (
    M2405_DOSSIER_SHA256,
    M2405_DOSSIER_SLICE,
    M2405_M2404_INPUT_MEDIA_TYPE,
    M2405_MODULE_ID,
    CalibrationSummary,
    CoverageStatus,
    CoverageSummary,
    EquityStatus,
    EvaluateBiomarkerPanelSubgroupEquityRequest,
    EvaluationConfiguration,
    EvaluationStatus,
    SubgroupDimension,
    SubgroupEvaluationReport,
    SubgroupPerformance,
    canonical_request_digest,
    contract_json_schemas,
    result_identifier,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_SCHEMA_COUNT = 8
_DIMENSIONS = tuple(SubgroupDimension)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(name.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(name: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name),
        role="evidence",
        claim="Caller-declared M24-05 subgroup equity evidence.",
    )


def _context(request_id: str = "m2405.request") -> ExecutionContext:
    evidence = _artifact("m2405.control.evidence")
    accepted = UpstreamDecisionReference(
        decision_id="m2405.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2405.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2405.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2405.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _configuration() -> EvaluationConfiguration:
    return EvaluationConfiguration(
        configuration_id="m2405.configuration",
        version="1.0.0",
        nominal_coverage_target=0.9,
        safety_floor=0.8,
        required_dimensions=_DIMENSIONS,
        evidence=(_evidence("m2405.configuration.evidence"),),
    )


def _performance(dimension: SubgroupDimension, index: int) -> SubgroupPerformance:
    return SubgroupPerformance(
        metric_id=f"m2405.performance.{index}",
        dimension=dimension,
        subgroup=f"{dimension.value}.reference",
        sample_size=100 + index,
        metric_name="balanced_accuracy",
        value=0.92,
        lower_bound=0.88,
        upper_bound=0.96,
        safety_floor=0.8,
        coverage_status=CoverageStatus.ADEQUATE,
        equity_status=EquityStatus.WITHIN_FLOOR,
        evidence=(_evidence(f"m2405.performance.{index}.evidence"),),
    )


def _calibration(dimension: SubgroupDimension, index: int) -> CalibrationSummary:
    return CalibrationSummary(
        calibration_id=f"m2405.calibration.{index}",
        dimension=dimension,
        subgroup=f"{dimension.value}.reference",
        expected_calibration_error=0.02,
        nominal_coverage=0.9,
        coverage_target=0.9,
        status=EvaluationStatus.EVALUATED,
        evidence=(_evidence(f"m2405.calibration.{index}.evidence"),),
    )


def _coverage(dimension: SubgroupDimension, index: int) -> CoverageSummary:
    return CoverageSummary(
        coverage_id=f"m2405.coverage.{index}",
        dimension=dimension,
        subgroup=f"{dimension.value}.reference",
        supported_examples=90,
        total_examples=100,
        coverage_fraction=0.9,
        status=CoverageStatus.ADEQUATE,
        evidence=(_evidence(f"m2405.coverage.{index}.evidence"),),
    )


def _request() -> EvaluateBiomarkerPanelSubgroupEquityRequest:
    upstream = _artifact("m2404.transport", M2405_M2404_INPUT_MEDIA_TYPE)
    return EvaluateBiomarkerPanelSubgroupEquityRequest(
        request_id="m2405.request",
        context=_context(),
        upstream_result=upstream,
        performance=tuple(
            _performance(dimension, index) for index, dimension in enumerate(_DIMENSIONS)
        ),
        calibration=tuple(
            _calibration(dimension, index) for index, dimension in enumerate(_DIMENSIONS)
        ),
        coverage=tuple(_coverage(dimension, index) for index, dimension in enumerate(_DIMENSIONS)),
        configuration=_configuration(),
        source_artifacts=(upstream, _artifact("m2405.policy")),
    )


def test_schema_binds_authority_and_safe_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    for schema in schemas.values():
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["moduleId"] == M2405_MODULE_ID
        assert metadata["authoritySha256"] == M2405_DOSSIER_SHA256
        assert metadata["authoritySlice"] == M2405_DOSSIER_SLICE
        assert metadata["unsupportedToNegative"] is False
        assert metadata["explicitAbstentionRequired"] is True
        assert metadata["rareContextRestrictionRequired"] is True


def test_request_digest_and_eight_dimension_closure() -> None:
    request = _request()
    assert canonical_request_digest(request) == canonical_request_digest(
        request.model_dump(mode="json")
    )
    assert result_identifier(request).startswith("result.")
    with pytest.raises(ValidationError, match="context request id"):
        EvaluateBiomarkerPanelSubgroupEquityRequest.model_validate(
            request.model_dump(mode="python") | {"context": _context("m2405.other")}, strict=True
        )
    with pytest.raises(ValidationError, match="include the upstream"):
        EvaluateBiomarkerPanelSubgroupEquityRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[1],)},
            strict=True,
        )
    with pytest.raises(ValidationError, match="performance must cover"):
        EvaluateBiomarkerPanelSubgroupEquityRequest.model_validate(
            request.model_dump(mode="python") | {"performance": request.performance[:-1]},
            strict=True,
        )


def test_request_rejects_wrong_media_duplicate_sources_and_upstream_drift() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="M24-04"):
        EvaluateBiomarkerPanelSubgroupEquityRequest.model_validate(
            request.model_dump(mode="python")
            | {
                "upstream_result": request.upstream_result.model_copy(
                    update={"media_type": "application/json"}
                )
            },
            strict=True,
        )
    with pytest.raises(ValidationError, match="source artifact ids"):
        EvaluateBiomarkerPanelSubgroupEquityRequest.model_validate(
            request.model_dump(mode="python")
            | {"source_artifacts": (request.source_artifacts[0],) * 2},
            strict=True,
        )


def test_bounds_fraction_and_configuration_closure() -> None:
    performance = _performance(SubgroupDimension.AGE, 0)
    with pytest.raises(ValidationError, match="bounds are not ordered"):
        SubgroupPerformance.model_validate(
            performance.model_dump(mode="python") | {"lower_bound": 0.99, "upper_bound": 0.9},
            strict=True,
        )
    with pytest.raises(ValidationError, match="coverage fraction"):
        CoverageSummary.model_validate(
            _coverage(SubgroupDimension.AGE, 0).model_dump(mode="python")
            | {"coverage_fraction": 0.8},
            strict=True,
        )
    with pytest.raises(ValidationError, match="at least 8"):
        EvaluationConfiguration.model_validate(
            _configuration().model_dump(mode="python") | {"required_dimensions": _DIMENSIONS[:-1]},
            strict=True,
        )


def test_report_rejects_duplicate_metric_calibration_or_coverage_ids() -> None:
    request = _request()
    report = SubgroupEvaluationReport(
        report_id="m2405.report",
        version="1.0.0",
        performance=(_performance(SubgroupDimension.AGE, 0),),
        calibration=(_calibration(SubgroupDimension.AGE, 0),),
        coverage=(_coverage(SubgroupDimension.AGE, 0),),
        configuration=_configuration(),
        evidence=(_evidence("m2405.report.evidence"),),
    )
    assert request.configuration.required_dimensions == _DIMENSIONS
    with pytest.raises(ValidationError, match="report ids must be unique"):
        SubgroupEvaluationReport.model_validate(
            report.model_dump(mode="python")
            | {
                "calibration": (
                    report.calibration[0].model_copy(
                        update={"calibration_id": report.performance[0].metric_id}
                    ),
                )
            },
            strict=True,
        )

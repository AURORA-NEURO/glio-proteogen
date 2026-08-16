"""Deterministic M24-05 evaluator fixtures."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m24_05 import (
    CalibrationSummary,
    CoverageStatus,
    CoverageSummary,
    EquityStatus,
    EvaluateBiomarkerPanelSubgroupEquityRequest,
    EvaluationConfiguration,
    EvaluationStatus,
    SubgroupDimension,
    SubgroupPerformance,
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

DIMENSIONS = tuple(SubgroupDimension)


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


def _context(request_id: str = "m2405.fixture.request") -> ExecutionContext:
    evidence = _artifact("m2405.fixture.control")
    accepted = UpstreamDecisionReference(
        decision_id="m2405.fixture.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2405.fixture.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2405.fixture.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2405.fixture.consent",
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
        configuration_id="m2405.fixture.configuration",
        version="1.0.0",
        nominal_coverage_target=0.9,
        safety_floor=0.8,
        required_dimensions=DIMENSIONS,
        evidence=(_evidence("m2405.fixture.configuration.evidence"),),
    )


def _performance(dimension: SubgroupDimension, index: int) -> SubgroupPerformance:
    return SubgroupPerformance(
        metric_id=f"m2405.fixture.performance.{index}",
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
        evidence=(_evidence(f"m2405.fixture.performance.{index}.evidence"),),
    )


def _calibration(dimension: SubgroupDimension, index: int) -> CalibrationSummary:
    return CalibrationSummary(
        calibration_id=f"m2405.fixture.calibration.{index}",
        dimension=dimension,
        subgroup=f"{dimension.value}.reference",
        expected_calibration_error=0.02,
        nominal_coverage=0.9,
        coverage_target=0.9,
        status=EvaluationStatus.EVALUATED,
        evidence=(_evidence(f"m2405.fixture.calibration.{index}.evidence"),),
    )


def _coverage(dimension: SubgroupDimension, index: int) -> CoverageSummary:
    return CoverageSummary(
        coverage_id=f"m2405.fixture.coverage.{index}",
        dimension=dimension,
        subgroup=f"{dimension.value}.reference",
        supported_examples=90,
        total_examples=100,
        coverage_fraction=0.9,
        status=CoverageStatus.ADEQUATE,
        evidence=(_evidence(f"m2405.fixture.coverage.{index}.evidence"),),
    )


def build_request() -> EvaluateBiomarkerPanelSubgroupEquityRequest:
    upstream = _artifact("m2404.fixture.transport", "application/vnd.glio-proteogen.m24-04+json")
    return EvaluateBiomarkerPanelSubgroupEquityRequest(
        request_id="m2405.fixture.request",
        context=_context(),
        upstream_result=upstream,
        performance=tuple(
            _performance(dimension, index) for index, dimension in enumerate(DIMENSIONS)
        ),
        calibration=tuple(
            _calibration(dimension, index) for index, dimension in enumerate(DIMENSIONS)
        ),
        coverage=tuple(_coverage(dimension, index) for index, dimension in enumerate(DIMENSIONS)),
        configuration=_configuration(),
        source_artifacts=(upstream, _artifact("m2405.fixture.policy")),
    )


def denied_request() -> EvaluateBiomarkerPanelSubgroupEquityRequest:
    request = build_request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": support})
    return request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )


def floor_request() -> EvaluateBiomarkerPanelSubgroupEquityRequest:
    request = build_request()
    performance = request.performance[0].model_copy(
        update={
            "value": 0.7,
            "lower_bound": 0.6,
            "upper_bound": 0.8,
            "equity_status": EquityStatus.BELOW_FLOOR,
        }
    )
    return request.model_copy(update={"performance": (performance, *request.performance[1:])})


def unsupported_request() -> EvaluateBiomarkerPanelSubgroupEquityRequest:
    request = build_request()
    coverage = request.coverage[0].model_copy(update={"status": CoverageStatus.NOT_EVALUABLE})
    return request.model_copy(update={"coverage": (coverage, *request.coverage[1:])})


def rare_limited_request() -> EvaluateBiomarkerPanelSubgroupEquityRequest:
    request = build_request()
    index = next(
        index
        for index, item in enumerate(request.coverage)
        if item.dimension is SubgroupDimension.RARE_BIOLOGICAL_STATE
    )
    rare = request.coverage[index].model_copy(update={"status": CoverageStatus.LIMITED})
    coverage = (*request.coverage[:index], rare, *request.coverage[index + 1 :])
    return request.model_copy(update={"coverage": coverage})


def calibration_abstained_request() -> EvaluateBiomarkerPanelSubgroupEquityRequest:
    request = build_request()
    calibration = request.calibration[0].model_copy(update={"status": EvaluationStatus.ABSTAINED})
    return request.model_copy(update={"calibration": (calibration, *request.calibration[1:])})

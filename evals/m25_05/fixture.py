"""Caller-declared deterministic M25-05 subgroup fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m25_05 import (
    M2505_M2504_INPUT_MEDIA_TYPE,
    CalibrationSummary,
    CoverageStatus,
    CoverageSummary,
    EquityStatus,
    EvaluateProteotypeSubgroupEquityRequest,
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

FIXTURE_REQUEST_ID = "m2505-fixture-request"
FIXTURE_DIGEST = "sha256:" + ("c" * 64)
FIXTURE_VERSION = "1.0.0"


def artifact(artifact_id: str, media_type: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        version=FIXTURE_VERSION,
        digest=FIXTURE_DIGEST,
        media_type=media_type,
    )


def evidence() -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=artifact("m2505-fixture-evidence"),
            role="evidence",
            claim="Caller-declared locked subgroup equity fixture evidence.",
        ),
    )


def context(request_id: str = FIXTURE_REQUEST_ID) -> ExecutionContext:
    control_evidence = artifact("m2505-control-evidence")

    def decision(decision_id: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=decision_id,
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=FIXTURE_VERSION,
            evidence=control_evidence,
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2505-fixture-actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("m2505-configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2505-identity",
                state=IdentityLineageState.RESOLVED,
                policy_version=FIXTURE_VERSION,
                binding_digest=FIXTURE_DIGEST,
                evidence=control_evidence,
            ),
            provenance=decision("m2505-provenance"),
            consent=ConsentReference(
                decision_id="m2505-consent",
                state=ConsentState.GRANTED,
                policy_version=FIXTURE_VERSION,
                evidence=control_evidence,
            ),
            quality=decision("m2505-quality"),
            support=decision("m2505-support"),
            intended_use=decision("m2505-intended-use"),
        ),
    )


def configuration() -> EvaluationConfiguration:
    return EvaluationConfiguration(
        configuration_id="m2505-locked-configuration",
        version=FIXTURE_VERSION,
        nominal_coverage_target=0.9,
        safety_floor=0.7,
        required_dimensions=tuple(SubgroupDimension),
        evidence=evidence(),
    )


def performance(
    *,
    equity_status: EquityStatus = EquityStatus.WITHIN_FLOOR,
    value: float = 0.82,
) -> tuple[SubgroupPerformance, ...]:
    return tuple(
        SubgroupPerformance(
            metric_id=f"m2505.metric.{dimension.value}",
            dimension=dimension,
            subgroup="all",
            sample_size=10,
            metric_name="balanced_accuracy",
            value=value,
            lower_bound=max(0.0, value - 0.04),
            upper_bound=min(1.0, value + 0.04),
            safety_floor=0.7,
            coverage_status=CoverageStatus.ADEQUATE,
            equity_status=equity_status,
            evidence=evidence(),
        )
        for dimension in SubgroupDimension
    )


def calibration(
    *,
    status: EvaluationStatus = EvaluationStatus.EVALUATED,
) -> tuple[CalibrationSummary, ...]:
    return tuple(
        CalibrationSummary(
            calibration_id=f"m2505.calibration.{dimension.value}",
            dimension=dimension,
            subgroup="all",
            expected_calibration_error=0.03,
            nominal_coverage=0.9,
            coverage_target=0.9,
            status=status,
            evidence=evidence(),
        )
        for dimension in SubgroupDimension
    )


def coverage(
    *,
    status: CoverageStatus = CoverageStatus.ADEQUATE,
) -> tuple[CoverageSummary, ...]:
    return tuple(
        CoverageSummary(
            coverage_id=f"m2505.coverage.{dimension.value}",
            dimension=dimension,
            subgroup="all",
            supported_examples=9,
            total_examples=10,
            coverage_fraction=0.9,
            status=status,
            evidence=evidence(),
        )
        for dimension in SubgroupDimension
    )


def build_request(
    *,
    performance_status: EquityStatus = EquityStatus.WITHIN_FLOOR,
    coverage_status: CoverageStatus = CoverageStatus.ADEQUATE,
    calibration_status: EvaluationStatus = EvaluationStatus.EVALUATED,
) -> EvaluateProteotypeSubgroupEquityRequest:
    upstream = artifact("m2505-upstream-result", M2505_M2504_INPUT_MEDIA_TYPE)
    return EvaluateProteotypeSubgroupEquityRequest(
        request_id=FIXTURE_REQUEST_ID,
        context=context(),
        upstream_result=upstream,
        performance=performance(
            equity_status=performance_status,
            value=0.6 if performance_status is EquityStatus.BELOW_FLOOR else 0.82,
        ),
        calibration=calibration(status=calibration_status),
        coverage=coverage(status=coverage_status),
        configuration=configuration(),
        source_artifacts=(upstream,),
    )


def denied_request() -> EvaluateProteotypeSubgroupEquityRequest:
    request = build_request()
    references = request.context.references
    denied = references.support.model_copy(update={"state": UpstreamDecisionState.REJECTED})
    return request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": references.model_copy(update={"support": denied})}
            )
        }
    )


__all__ = [
    "FIXTURE_DIGEST",
    "FIXTURE_REQUEST_ID",
    "build_request",
    "context",
    "denied_request",
]

"""Frozen caller-declared M22-05 subgroup equity fixture."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m22_05 import (
    M2205_M2204_INPUT_MEDIA_TYPE,
    CalibrationSummary,
    CoverageStatus,
    CoverageSummary,
    EquityStatus,
    EvaluateProteinRnaDiscordanceSubgroupEquityRequest,
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
        claim="Frozen M22-05 subgroup fixture evidence.",
    )


def _context(request_id: str) -> ExecutionContext:
    artifact = _artifact("m2205.context")
    accepted = UpstreamDecisionReference(
        decision_id="m2205.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2205.fixture.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2205.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "1" * 64,
                evidence=artifact,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2205.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def build_request() -> EvaluateProteinRnaDiscordanceSubgroupEquityRequest:
    """Return the frozen normal subgroup evaluation request."""

    upstream = _artifact("m2204.evaluator", M2205_M2204_INPUT_MEDIA_TYPE)
    return EvaluateProteinRnaDiscordanceSubgroupEquityRequest(
        request_id="m2205.fixture.request",
        context=_context("m2205.fixture.request"),
        upstream_result=upstream,
        performance=(
            SubgroupPerformance(
                metric_id="m2205.age.performance",
                dimension=SubgroupDimension.AGE,
                subgroup="adult",
                sample_size=20,
                metric_name="balanced_accuracy",
                value=0.7,
                lower_bound=0.4,
                upper_bound=0.8,
                safety_floor=0.6,
                coverage_status=CoverageStatus.ADEQUATE,
                equity_status=EquityStatus.WITHIN_FLOOR,
                evidence=(_evidence("m2205.performance.evidence"),),
            ),
        ),
        calibration=(
            CalibrationSummary(
                calibration_id="m2205.age.calibration",
                dimension=SubgroupDimension.AGE,
                subgroup="adult",
                expected_calibration_error=0.04,
                nominal_coverage=0.9,
                coverage_target=0.9,
                status=EvaluationStatus.EVALUATED,
                evidence=(_evidence("m2205.calibration.evidence"),),
            ),
        ),
        coverage=(
            CoverageSummary(
                coverage_id="m2205.age.coverage",
                dimension=SubgroupDimension.AGE,
                subgroup="adult",
                supported_examples=8,
                total_examples=10,
                coverage_fraction=0.8,
                status=CoverageStatus.ADEQUATE,
                evidence=(_evidence("m2205.coverage.evidence"),),
            ),
        ),
        configuration=EvaluationConfiguration(
            configuration_id="m2205.configuration",
            version="1.0.0",
            nominal_coverage_target=0.9,
            safety_floor=0.6,
            required_dimensions=tuple(SubgroupDimension),
            evidence=(_evidence("m2205.configuration.evidence"),),
        ),
        source_artifacts=(upstream, _artifact("m2205.subgroup.material")),
    )


def denied_request() -> EvaluateProteinRnaDiscordanceSubgroupEquityRequest:
    """Return a request denied by the caller-declared support control."""

    request = build_request()
    rejected = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": rejected})}
    )
    return request.model_copy(update={"context": context})


def unsupported_request() -> EvaluateProteinRnaDiscordanceSubgroupEquityRequest:
    """Return a request whose coverage requires explicit abstention."""

    request = build_request()
    coverage = request.coverage[0].model_copy(update={"status": CoverageStatus.UNSUPPORTED})
    return request.model_copy(update={"coverage": (coverage,)})


__all__ = ["build_request", "denied_request", "unsupported_request"]

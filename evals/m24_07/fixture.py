"""Frozen, self-contained M24-07 evaluator fixture."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m24_07 import (
    M2407_M2406_INPUT_MEDIA_TYPE,
    EvaluateBiomarkerPanelHumanFactorsRequest,
    FallbackScenario,
    OperationalConfiguration,
    OperationalDimension,
    OperationalMetric,
    OperationalStatus,
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


def artifact(seed: str) -> ArtifactReference:
    value = seed[0] if seed and seed[0] in "0123456789abcdef" else "a"
    return ArtifactReference(
        artifact_id=f"m2407.fixture.{seed}",
        version="1.0.0",
        digest="sha256:" + value * 64,
        media_type="application/vnd.glio-proteogen.evidence+json",
    )


def evidence(seed: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=artifact(seed), role="evidence", claim="locked fixture material"
        ),
    )


def context() -> ExecutionContext:
    def accepted(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2407.fixture.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact(role[0]),
        )

    return ExecutionContext(
        request_id="m2407.fixture.context",
        actor_id="m2407.fixture.actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2407.fixture.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "b" * 64,
                evidence=artifact("b"),
            ),
            provenance=accepted("provenance"),
            consent=ConsentReference(
                decision_id="m2407.fixture.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact("c"),
            ),
            quality=accepted("quality"),
            support=accepted("support"),
            intended_use=accepted("intendeduse"),
        ),
    )


def metric(
    dimension: OperationalDimension,
    status: OperationalStatus = OperationalStatus.PASS,
) -> OperationalMetric:
    return OperationalMetric(
        metric_id=f"m2407.fixture.metric.{dimension.value}",
        dimension=dimension,
        metric_name=f"{dimension.value} score",
        observed_value=1.0,
        target_value=1.0,
        tolerance=0.1,
        sample_size=20,
        status=status,
        evidence=evidence(dimension.value[0]),
    )


def fallback(
    dimension: OperationalDimension,
    status: OperationalStatus = OperationalStatus.PASS,
) -> FallbackScenario:
    return FallbackScenario(
        scenario_id=f"m2407.fixture.fallback.{dimension.value}",
        dimension=dimension,
        trigger=f"{dimension.value} challenge",
        fallback_path="review and abstain",
        recovery_seconds=4.0,
        fallback_available=status is OperationalStatus.PASS,
        status=status,
        evidence=evidence(dimension.value[-1]),
    )


def request() -> EvaluateBiomarkerPanelHumanFactorsRequest:
    return EvaluateBiomarkerPanelHumanFactorsRequest(
        request_id="m2407.fixture.request",
        context=context(),
        upstream_result=ArtifactReference(
            artifact_id="m2406.fixture.result",
            version="0.1.0-provisional",
            digest="sha256:" + "e" * 64,
            media_type=M2407_M2406_INPUT_MEDIA_TYPE,
        ),
        metrics=tuple(metric(dimension) for dimension in OperationalDimension),
        fallbacks=tuple(
            fallback(dimension)
            for dimension in (
                OperationalDimension.DOWNTIME,
                OperationalDimension.RECOVERY,
                OperationalDimension.FALLBACK,
            )
        ),
        configuration=OperationalConfiguration(
            configuration_id="m2407.fixture.configuration",
            version="1.0.0",
            required_dimensions=tuple(OperationalDimension),
            evidence=evidence("d"),
        ),
        source_artifacts=(artifact("e"),),
    )

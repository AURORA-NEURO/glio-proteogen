"""Caller-declared deterministic M25-07 operational fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m25_07 import (
    M2507_M2506_INPUT_MEDIA_TYPE,
    EvaluateProteotypeHumanFactorsRequest,
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

FIXTURE_REQUEST_ID = "m2507-fixture-request"
FIXTURE_DIGEST = "sha256:" + ("d" * 64)
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
            reference=artifact("m2507-fixture-evidence"),
            role="evidence",
            claim="Caller-declared locked operational fixture evidence.",
        ),
    )


def context(request_id: str = FIXTURE_REQUEST_ID) -> ExecutionContext:
    control_evidence = artifact("m2507-control-evidence")

    def decision(decision_id: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=decision_id,
            state=UpstreamDecisionState.ACCEPTED,
            policy_version=FIXTURE_VERSION,
            evidence=control_evidence,
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2507-fixture-actor",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("m2507-configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2507-identity",
                state=IdentityLineageState.RESOLVED,
                policy_version=FIXTURE_VERSION,
                binding_digest=FIXTURE_DIGEST,
                evidence=control_evidence,
            ),
            provenance=decision("m2507-provenance"),
            consent=ConsentReference(
                decision_id="m2507-consent",
                state=ConsentState.GRANTED,
                policy_version=FIXTURE_VERSION,
                evidence=control_evidence,
            ),
            quality=decision("m2507-quality"),
            support=decision("m2507-support"),
            intended_use=decision("m2507-intended-use"),
        ),
    )


def configuration() -> OperationalConfiguration:
    return OperationalConfiguration(
        configuration_id="m2507-locked-configuration",
        version=FIXTURE_VERSION,
        required_dimensions=tuple(OperationalDimension),
        evidence=evidence(),
    )


def metrics(
    *,
    status: OperationalStatus = OperationalStatus.PASS,
    observed_value: float = 0.9,
) -> tuple[OperationalMetric, ...]:
    return tuple(
        OperationalMetric(
            metric_id=f"m2507.metric.{dimension.value}",
            dimension=dimension,
            metric_name=dimension.value,
            observed_value=observed_value,
            target_value=0.9,
            tolerance=0.1,
            sample_size=10,
            status=status,
            evidence=evidence(),
        )
        for dimension in OperationalDimension
    )


def fallbacks(
    *,
    status: OperationalStatus = OperationalStatus.PASS,
    fallback_available: bool = True,
) -> tuple[FallbackScenario, ...]:
    effective_status = OperationalStatus.FAIL if not fallback_available else status
    return tuple(
        FallbackScenario(
            scenario_id=f"m2507.fallback.{dimension.value}",
            dimension=dimension,
            trigger=f"declared {dimension.value} disruption",
            fallback_path="manual review and safe abstention",
            recovery_seconds=30.0,
            fallback_available=fallback_available,
            status=effective_status,
            evidence=evidence(),
        )
        for dimension in (
            OperationalDimension.DOWNTIME,
            OperationalDimension.RECOVERY,
            OperationalDimension.FALLBACK,
        )
    )


def build_request(
    *,
    metric_status: OperationalStatus = OperationalStatus.PASS,
    fallback_status: OperationalStatus = OperationalStatus.PASS,
    fallback_available: bool = True,
) -> EvaluateProteotypeHumanFactorsRequest:
    upstream = artifact("m2507-upstream-result", M2507_M2506_INPUT_MEDIA_TYPE)
    return EvaluateProteotypeHumanFactorsRequest(
        request_id=FIXTURE_REQUEST_ID,
        context=context(),
        upstream_result=upstream,
        metrics=metrics(status=metric_status),
        fallbacks=fallbacks(status=fallback_status, fallback_available=fallback_available),
        configuration=configuration(),
        source_artifacts=(upstream,),
    )


def denied_request() -> EvaluateProteotypeHumanFactorsRequest:
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

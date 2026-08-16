"""Frozen caller-declared M23-07 operational evaluator fixture."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m23_07 import (
    M2307_M2306_INPUT_MEDIA_TYPE,
    EvaluateVariantPeptideHumanFactorsRequest,
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
        claim="Frozen M23-07 operational fixture evidence.",
    )


def _context(request_id: str) -> ExecutionContext:
    artifact = _artifact("m2307.context")
    accepted = UpstreamDecisionReference(
        decision_id="m2307.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )
    return ExecutionContext(
        request_id=request_id,
        actor_id="m2307.fixture.actor",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="m2307.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest="sha256:" + "1" * 64,
                evidence=artifact,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="m2307.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def build_request() -> EvaluateVariantPeptideHumanFactorsRequest:
    """Return the frozen supported operational evaluation request."""

    evidence = (_evidence("m2307.operational.evidence"),)
    dimensions = tuple(OperationalDimension)
    metrics = tuple(
        OperationalMetric(
            metric_id=f"m2307.metric.{index}",
            dimension=dimension,
            metric_name=dimension.value,
            observed_value=1.0,
            target_value=1.0,
            tolerance=0.1,
            sample_size=20,
            status=OperationalStatus.PASS,
            evidence=evidence,
        )
        for index, dimension in enumerate(dimensions)
    )
    fallbacks = tuple(
        FallbackScenario(
            scenario_id=f"m2307.fallback.{dimension.value}",
            dimension=dimension,
            trigger="primary path unavailable",
            fallback_path="review queue",
            recovery_seconds=1.0,
            fallback_available=True,
            status=OperationalStatus.PASS,
            evidence=evidence,
        )
        for dimension in (
            OperationalDimension.DOWNTIME,
            OperationalDimension.RECOVERY,
            OperationalDimension.FALLBACK,
        )
    )
    configuration = OperationalConfiguration(
        configuration_id="m2307.configuration",
        version="1.0.0",
        required_dimensions=dimensions,
        evidence=(_evidence("m2307.configuration.evidence"),),
    )
    upstream = _artifact("m2306.evaluator", M2307_M2306_INPUT_MEDIA_TYPE)
    return EvaluateVariantPeptideHumanFactorsRequest(
        request_id="m2307.fixture.request",
        context=_context("m2307.fixture.request"),
        upstream_result=upstream,
        metrics=metrics,
        fallbacks=fallbacks,
        configuration=configuration,
        source_artifacts=(upstream,),
    )


def denied_request() -> EvaluateVariantPeptideHumanFactorsRequest:
    """Return a request denied by the caller-declared consent control."""

    request = build_request()
    withheld = request.context.references.consent.model_copy(
        update={"state": ConsentState.WITHHELD}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"consent": withheld})}
    )
    return request.model_copy(update={"context": context})


def unsupported_request() -> EvaluateVariantPeptideHumanFactorsRequest:
    """Return a request whose operational material requires abstention."""

    request = build_request()
    metric = request.metrics[0].model_copy(update={"status": OperationalStatus.NOT_EVALUABLE})
    return request.model_copy(update={"metrics": (metric, *request.metrics[1:])})


def failed_request() -> EvaluateVariantPeptideHumanFactorsRequest:
    """Return a request with a supported but failed latency metric."""

    request = build_request()
    metric = request.metrics[3].model_copy(
        update={"observed_value": 2.0, "target_value": 1.0, "status": OperationalStatus.FAIL}
    )
    return request.model_copy(
        update={"metrics": (*request.metrics[:3], metric, *request.metrics[4:])}
    )


__all__ = ["build_request", "denied_request", "failed_request", "unsupported_request"]

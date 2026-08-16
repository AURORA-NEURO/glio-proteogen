"""Frozen, caller-declared M26-05 telemetry fixture for evaluation and benchmarks."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from glio_proteogen.contracts.m26_05 import (
    M2605_M2604_INPUT_MEDIA_TYPE,
    DashboardDefinition,
    EmitProteomicsTelemetryRequest,
    TelemetryMetricKind,
    TelemetrySample,
    TelemetryUnit,
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

FIXTURE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2605.fixture.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type=media_type,
    )


def evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact(f"evidence-{label}"),
        role="evidence",
        claim="Frozen synthetic M26-05 telemetry evidence retained for review.",
    )


def context() -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2605.fixture.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=artifact(f"control-{label}"),
        )

    return ExecutionContext(
        request_id="m2605.fixture.context",
        actor_id="m2605.fixture.actor",
        occurred_at=FIXTURE_TIMESTAMP,
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2605.fixture.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=artifact("identity").digest,
                evidence=artifact("identity-evidence"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2605.fixture.decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def make_request() -> EmitProteomicsTelemetryRequest:
    upstream = artifact("m2604", M2605_M2604_INPUT_MEDIA_TYPE)
    values: dict[TelemetryMetricKind, tuple[float, TelemetryUnit]] = {
        TelemetryMetricKind.INPUT_QUALITY: (0.9, TelemetryUnit.SCORE),
        TelemetryMetricKind.MODEL_BEHAVIOR: (0.8, TelemetryUnit.SCORE),
        TelemetryMetricKind.UNCERTAINTY: (0.1, TelemetryUnit.RATIO),
        TelemetryMetricKind.ABSTENTION: (0.02, TelemetryUnit.RATIO),
        TelemetryMetricKind.DRIFT: (0.1, TelemetryUnit.SCORE),
        TelemetryMetricKind.LATENCY: (12.0, TelemetryUnit.MILLISECONDS),
        TelemetryMetricKind.ERRORS: (0.01, TelemetryUnit.RATIO),
        TelemetryMetricKind.RESOURCES: (1024.0, TelemetryUnit.BYTES),
    }
    samples = tuple(
        TelemetrySample(
            sample_id=f"m2605.fixture.sample.{metric.value}",
            metric=metric,
            value=value,
            unit=unit,
            observed_at=FIXTURE_TIMESTAMP + timedelta(seconds=index),
            source="m2605.frozen.synthetic",
            evidence=(evidence(metric.value),),
        )
        for index, (metric, (value, unit)) in enumerate(values.items())
    )
    dashboards = (
        DashboardDefinition(
            dashboard_id="m2605.fixture.dashboard.operations",
            title="Operations telemetry",
            metrics=(TelemetryMetricKind.INPUT_QUALITY, TelemetryMetricKind.MODEL_BEHAVIOR),
            owner="m2605-review",
            refresh_seconds=60,
            evidence=(evidence("operations-dashboard"),),
        ),
        DashboardDefinition(
            dashboard_id="m2605.fixture.dashboard.risk",
            title="Risk telemetry",
            metrics=(TelemetryMetricKind.DRIFT, TelemetryMetricKind.ERRORS),
            owner="m2605-review",
            refresh_seconds=120,
            evidence=(evidence("risk-dashboard"),),
        ),
    )
    return EmitProteomicsTelemetryRequest(
        request_id="m2605.fixture.request",
        context=context(),
        upstream_result=upstream,
        requested_metrics=tuple(values),
        samples=samples,
        dashboard_definitions=dashboards,
        source_artifacts=(upstream,),
    )


__all__ = ["FIXTURE_TIMESTAMP", "artifact", "context", "evidence", "make_request"]

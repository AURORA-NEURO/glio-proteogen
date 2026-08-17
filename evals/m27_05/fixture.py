"""Representative caller-declared M27-05 request builders."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m27_05 import (
    M2705_M2704_INPUT_MEDIA_TYPE,
    DashboardDefinition,
    EmitProteomicsTelemetryRequest,
    TelemetryMetricKind,
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


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2705.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type=media_type,
    )


def _context(request_id: str) -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2705.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{label}"),
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2705.actor.telemetry",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2705.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_artifact("identity").digest,
                evidence=_artifact("identity-evidence"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2705.decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def build_request(
    request_id: str = "m2705.request.telemetry",
    *,
    upstream_media_type: str = M2705_M2704_INPUT_MEDIA_TYPE,
) -> EmitProteomicsTelemetryRequest:
    """Build the deterministic supported M27-05 workload."""

    evidence = (
        EvidenceReference(
            reference=_artifact("telemetry-evidence"),
            role="evidence",
            claim="Caller-declared M27-05 observability evidence.",
        ),
    )
    return EmitProteomicsTelemetryRequest(
        request_id=request_id,
        context=_context(request_id),
        upstream_result=_artifact("m2704-result", upstream_media_type),
        requested_metrics=tuple(TelemetryMetricKind),
        dashboard_definitions=(
            DashboardDefinition(
                dashboard_id="m2705.dashboard.operations",
                title="Complex activity operations telemetry",
                metrics=tuple(TelemetryMetricKind),
                owner="caller-declared-operations",
                refresh_seconds=60,
                evidence=evidence,
            ),
        ),
        source_artifacts=(_artifact("search-quant"), _artifact("observability")),
    )


__all__ = ["build_request"]

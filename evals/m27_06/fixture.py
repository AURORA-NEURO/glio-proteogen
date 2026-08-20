"""Deterministic caller-declared M27-06 security workload."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m27_06 import (
    M2706_M2705_INPUT_MEDIA_TYPE,
    EvaluateComplexActivitySecurityAccessRequest,
    SecurityControlKind,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2706.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type=media_type,
    )


def _context(request_id: str) -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2706.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{label}"),
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2706.actor.security",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2706.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_artifact("identity").digest,
                evidence=_artifact("identity-evidence"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2706.decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def build_request(  # noqa: PLR0913 - fixture exposes each security axis.
    request_id: str = "m2706.request.security",
    *,
    upstream_media_type: str = M2706_M2705_INPUT_MEDIA_TYPE,
    principal: str = "service:m27-06",
    resource: str = "dataset:complex-activity",
    action: str = "read",
    with_consent: bool = True,
) -> EvaluateComplexActivitySecurityAccessRequest:
    """Build a deterministic supported security request."""

    return EvaluateComplexActivitySecurityAccessRequest(
        request_id=request_id,
        context=_context(request_id),
        upstream_result=_artifact("m2705-result", upstream_media_type),
        principal=principal,
        resource=resource,
        action=action,
        policy_version="1.0.0",
        requested_controls=tuple(SecurityControlKind),
        consent_reference=_artifact("consent") if with_consent else None,
        source_artifacts=(_artifact("security-policy"), _artifact("audit-log")),
    )


__all__ = ["build_request"]

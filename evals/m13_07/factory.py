"""Frozen, caller-declared M13-07 evaluator scenarios."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m13_07 import (
    M1307_M1306_RESULT_MEDIA_TYPE,
    AdjudicateProteotypePlausibilityRequest,
    ControlKind,
    ControlOutcome,
    PlausibilityControl,
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


def _digest(seed: int) -> str:
    return f"sha256:{seed:064x}"


def artifact(name: str, seed: int, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_digest(seed),
        media_type=media_type,
    )


def context(*, support: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED) -> ExecutionContext:
    policy = "1.0.0"
    return ExecutionContext(
        request_id="context-request",
        actor_id="evaluator",
        occurred_at=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="config-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=policy,
                evidence=artifact("configuration", 1),
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="identity-decision",
                state=IdentityLineageState.RESOLVED,
                policy_version=policy,
                binding_digest=_digest(8),
                evidence=artifact("identity", 2),
            ),
            provenance=UpstreamDecisionReference(
                decision_id="provenance-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=policy,
                evidence=artifact("provenance", 3),
            ),
            consent=ConsentReference(
                decision_id="consent-decision",
                state=ConsentState.GRANTED,
                policy_version=policy,
                evidence=artifact("consent", 4),
            ),
            quality=UpstreamDecisionReference(
                decision_id="quality-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=policy,
                evidence=artifact("quality", 5),
            ),
            support=UpstreamDecisionReference(
                decision_id="support-decision",
                state=support,
                policy_version=policy,
                evidence=artifact("support", 6),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="intended-use-decision",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version=policy,
                evidence=artifact("intended-use", 7),
            ),
        ),
    )


def controls(outcome: ControlOutcome = ControlOutcome.PASSED) -> tuple[PlausibilityControl, ...]:
    kinds = (
        ControlKind.ORTHOGONAL_EVIDENCE,
        ControlKind.KNOWN_CONTROL,
        ControlKind.DIRECTION,
        ControlKind.CONSERVATION,
        ControlKind.ASSAY_PHYSICS,
        ControlKind.COMPETING_MECHANISM,
    )
    return tuple(
        PlausibilityControl(
            control_id=f"control-{index}",
            kind=kind,
            criterion=f"criterion-{kind.value}",
            expected_direction="consistent" if kind is ControlKind.DIRECTION else None,
            required_evidence=(
                EvidenceReference(
                    reference=artifact(f"control-evidence-{index}", 20 + index),
                    role="evidence",
                    claim="caller-declared control evidence",
                ),
            ),
            declared_outcome=outcome,
            observed_direction="consistent" if kind is ControlKind.DIRECTION else None,
            is_negative_control=kind is ControlKind.KNOWN_CONTROL,
        )
        for index, kind in enumerate(kinds)
    )


def build_request(
    *,
    outcome: ControlOutcome = ControlOutcome.PASSED,
    conflict: bool = False,
    support: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED,
) -> AdjudicateProteotypePlausibilityRequest:
    return AdjudicateProteotypePlausibilityRequest(
        request_id="request-m1307",
        context=context(support=support),
        mechanism_inference_result=artifact("mechanism-result", 10, M1307_M1306_RESULT_MEDIA_TYPE),
        controls=controls(outcome),
        candidate_mechanisms=("mechanism-a", "mechanism-b"),
        conflict_declared=conflict,
        source_artifacts=(artifact("proteome-source", 11),),
    )


__all__ = ["artifact", "build_request", "context", "controls"]

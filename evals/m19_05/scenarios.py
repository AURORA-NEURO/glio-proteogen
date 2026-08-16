"""Deterministic caller-declared M19-05 evaluator scenarios."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m19_05 import (
    M1905_M1904_RESULT_MEDIA_TYPE,
    OrderingPolicy,
    PresentationConfiguration,
    PresentationPolicy,
    PresentProteotypeHumanReviewWorkspaceRequest,
    ReviewItem,
    ReviewItemStatus,
    ViewKind,
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


def _artifact(
    artifact_id: str,
    character: str,
    media_type: str = "application/octet-stream",
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        version="1.0.0",
        digest="sha256:" + character * 64,
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M19-05 review evidence.",
    )


def _controls(*, accepted: bool = True) -> ContextReferences:
    decision_state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    identity_state = IdentityLineageState.RESOLVED if accepted else IdentityLineageState.CONFLICTED
    consent_state = ConsentState.GRANTED if accepted else ConsentState.WITHHELD
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config",
            state=decision_state,
            policy_version="1.0.0",
            evidence=_artifact("control.config", "1"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=identity_state,
            policy_version="1.0.0",
            binding_digest="sha256:" + "2" * 64,
            evidence=_artifact("control.identity", "2"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=decision_state,
            policy_version="1.0.0",
            evidence=_artifact("control.provenance", "3"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=consent_state,
            policy_version="1.0.0",
            evidence=_artifact("control.consent", "4"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=decision_state,
            policy_version="1.0.0",
            evidence=_artifact("control.quality", "5"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=decision_state,
            policy_version="1.0.0",
            evidence=_artifact("control.support", "6"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=decision_state,
            policy_version="1.0.0",
            evidence=_artifact("control.intended", "7"),
        ),
    )


def build_request(
    *,
    item_status: ReviewItemStatus = ReviewItemStatus.SUPPORTED,
    accepted: bool = True,
) -> PresentProteotypeHumanReviewWorkspaceRequest:
    upstream = _artifact("upstream.m1904", "8", M1905_M1904_RESULT_MEDIA_TYPE)
    item_artifacts = tuple(_artifact(f"item.{index}", chr(97 + index)) for index in range(6))
    items = tuple(
        ReviewItem(
            item_id=f"item.{index}",
            view_kind=view,
            title=view.value.replace("_", " ").title(),
            position=index,
            status=item_status,
            evidence=(_evidence(item_artifacts[index]),),
            uncertainty_summary="Caller-declared uncertainty remains visible to the reviewer.",
            evidence_summary="Caller-declared evidence summary is attributable.",
            provenance_artifact=item_artifacts[index],
        )
        for index, view in enumerate(ViewKind)
    )
    configuration_artifact = _artifact("configuration.m1905", "9")
    configuration = PresentationConfiguration(
        configuration_id="configuration.m1905",
        version="1.0.0",
        method="locked-human-review-presentation",
        model_reference=_artifact("model.m1905", "0"),
        evidence=(_evidence(configuration_artifact),),
    )
    policy = PresentationPolicy(
        required_views=tuple(ViewKind),
        default_ordering=OrderingPolicy.SAFE_DEFAULT,
        maximum_items=6,
        configuration=configuration,
    )
    return PresentProteotypeHumanReviewWorkspaceRequest(
        request_id="request.m1905",
        context=ExecutionContext(
            request_id="request.m1905",
            actor_id="actor.synthetic",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            references=_controls(accepted=accepted),
        ),
        aligned_evidence_bundle=upstream,
        policy=policy,
        review_items=items,
        source_artifacts=(upstream, *item_artifacts),
    )


__all__ = ["build_request"]

"""Frozen caller-declared M20-05 workspace scenarios."""

from __future__ import annotations

from datetime import UTC, datetime

from glio_proteogen.contracts.m20_05 import (
    M2005_M2004_RESULT_MEDIA_TYPE,
    NextAction,
    OrderingPolicy,
    PresentationConfiguration,
    PresentationPolicy,
    PresentProteinSubtypeHumanReviewWorkspaceRequest,
    ReviewItem,
    ReviewItemStatus,
    ViewKind,
)
from glio_proteogen.kernel.canonical import sha256_digest
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


def artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2005.eval.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2005-eval:{name}:{media_type}"),
        media_type=media_type,
    )


def evidence(item: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=item,
        role="evidence",
        claim="Frozen caller-declared M20-05 review evidence.",
    )


def decision(name: str, item: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2005.eval.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=item,
    )


def context(request_id: str = "request.m2005.eval") -> ExecutionContext:
    controls = {
        name: artifact(f"control-{name}")
        for name in (
            "configuration",
            "provenance",
            "quality",
            "support",
            "intended-use",
            "consent",
            "identity",
        )
    }
    return ExecutionContext(
        request_id=request_id,
        actor_id="actor.m2005.eval",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", controls["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2005.eval.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2005-eval:identity"),
                evidence=controls["identity"],
            ),
            provenance=decision("provenance", controls["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m2005.eval.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=controls["consent"],
            ),
            quality=decision("quality", controls["quality"]),
            support=decision("support", controls["support"]),
            intended_use=decision("intended-use", controls["intended-use"]),
        ),
    )


def policy() -> PresentationPolicy:
    model = artifact("presentation-model")
    return PresentationPolicy(
        required_views=tuple(ViewKind),
        default_ordering=OrderingPolicy.SAFE_DEFAULT,
        maximum_items=32,
        configuration=PresentationConfiguration(
            configuration_id="configuration.m2005.eval",
            version="1.0.0",
            method="locked_human_review_workspace",
            model_reference=model,
            evidence=(evidence(model),),
        ),
    )


def item(
    view: ViewKind,
    position: int,
    status: ReviewItemStatus = ReviewItemStatus.SUPPORTED,
) -> ReviewItem:
    source = artifact(f"item-{position}")
    escalation = None
    discrepancies: tuple[str, ...] = ()
    if status in {
        ReviewItemStatus.CONFLICTED,
        ReviewItemStatus.UNRESOLVED,
        ReviewItemStatus.ABSTAINED,
    }:
        discrepancies = (f"discrepancy.m2005.eval.{position}",)
        escalation = NextAction(
            action_id=f"action.m2005.eval.{position}",
            label="Review declared discrepancy",
            rationale="An authorized reviewer must resolve the declared item state.",
        )
    return ReviewItem(
        item_id=f"item.m2005.eval.{position}",
        view_kind=view,
        title=f"{view.value} review",
        position=position,
        status=status,
        evidence_summary="Caller-declared evidence remains attributable and visible.",
        uncertainty_summary="Uncertainty is displayed without conversion to a negative claim.",
        evidence=(evidence(source),),
        discrepancy_ids=discrepancies,
        provenance_artifact=source,
        next_action=escalation,
    )


def build_request() -> PresentProteinSubtypeHumanReviewWorkspaceRequest:
    aligned = artifact("aligned", M2005_M2004_RESULT_MEDIA_TYPE)
    current_policy = policy()
    items = tuple(
        item(view, position) for position, view in enumerate(current_policy.required_views)
    )
    return PresentProteinSubtypeHumanReviewWorkspaceRequest(
        request_id="request.m2005.eval",
        context=context(),
        aligned_evidence_bundle=aligned,
        policy=current_policy,
        review_items=items,
        source_artifacts=(aligned, *(review.provenance_artifact for review in items)),
    )


def conflicted_request() -> PresentProteinSubtypeHumanReviewWorkspaceRequest:
    request = build_request()
    conflicted = item(request.review_items[0].view_kind, 0, ReviewItemStatus.CONFLICTED)
    return request.model_copy(update={"review_items": (conflicted, *request.review_items[1:])})


def abstained_request() -> PresentProteinSubtypeHumanReviewWorkspaceRequest:
    request = build_request()
    abstained = item(request.review_items[0].view_kind, 0, ReviewItemStatus.ABSTAINED)
    return request.model_copy(update={"review_items": (abstained, *request.review_items[1:])})


def denied_request() -> PresentProteinSubtypeHumanReviewWorkspaceRequest:
    request = build_request()
    denied = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": denied})
    return request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )


__all__ = ["abstained_request", "build_request", "conflicted_request", "denied_request"]

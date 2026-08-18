"""Frozen synthetic evaluator for M17-05 workflow presentation."""

# Synthetic metadata builders intentionally keep scenario arguments explicit.
# ruff: noqa: E501, FBT001, FBT002, T201

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m17_05 import (
    M1705_M1702_RESULT_MEDIA_TYPE,
    NextAction,
    OrderingPolicy,
    PresentationConfiguration,
    PresentationPolicy,
    PresentVariantPeptideHumanReviewWorkspaceRequest,
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
from glio_proteogen.modules.c17_metabolomic_lipidomic.m17_05_workflow_presentation_service import (
    M1705AuthorizationError,
    M1705WorkflowPresentationEngine,
)

FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m17_05" / "scenarios.json"


def _artifact(name: str, digest_char: str, media: str = "application/octet-stream") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest="sha256:" + digest_char * 64,
        media_type=media,
    )


def _evidence(name: str, digest_char: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(name, digest_char),
        role="evidence",
        claim="Synthetic caller-declared M17-05 review evidence.",
    )


def _controls(accepted: bool = True) -> ContextReferences:
    state = UpstreamDecisionState.ACCEPTED if accepted else UpstreamDecisionState.REJECTED
    return ContextReferences(
        approved_configuration=UpstreamDecisionReference(
            decision_id="decision.config",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("control-config", "1"),
        ),
        identity_lineage=IdentityLineageReference(
            decision_id="decision.identity",
            state=IdentityLineageState.RESOLVED if accepted else IdentityLineageState.CONFLICTED,
            policy_version="1.0.0",
            binding_digest="sha256:" + "2" * 64,
            evidence=_artifact("control-identity", "2"),
        ),
        provenance=UpstreamDecisionReference(
            decision_id="decision.provenance",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("control-provenance", "3"),
        ),
        consent=ConsentReference(
            decision_id="decision.consent",
            state=ConsentState.GRANTED if accepted else ConsentState.WITHHELD,
            policy_version="1.0.0",
            evidence=_artifact("control-consent", "4"),
        ),
        quality=UpstreamDecisionReference(
            decision_id="decision.quality",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("control-quality", "5"),
        ),
        support=UpstreamDecisionReference(
            decision_id="decision.support",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("control-support", "6"),
        ),
        intended_use=UpstreamDecisionReference(
            decision_id="decision.intended",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact("control-intended", "7"),
        ),
    )


def _item(
    index: int,
    view_kind: ViewKind,
    status: ReviewItemStatus,
) -> ReviewItem:
    evidence = _evidence(f"item-evidence-{index}", "abcdef"[index])
    provenance = _artifact(f"item-provenance-{index}", "123456"[index])
    next_action = None
    if view_kind is ViewKind.NEXT_ACTION:
        next_action = NextAction(
            action_id="action.review",
            label="Review caller-declared evidence",
            rationale="A human reviewer must inspect the workspace before claim promotion.",
            required_evidence=(evidence.reference,),
        )
    return ReviewItem(
        item_id=f"item.m1705.{index}",
        view_kind=view_kind,
        title=f"Synthetic {view_kind.value} view",
        position=index,
        status=status,
        evidence_summary="Caller-declared evidence summary remains attributable and visible.",
        uncertainty_summary="Caller-declared uncertainty requires human review.",
        evidence=(evidence,),
        discrepancy_ids=("discrepancy.synthetic",) if status is ReviewItemStatus.CONFLICTED else (),
        provenance_artifact=provenance,
        next_action=next_action,
    )


def build_scenario_request(
    scenario: str = "supported",
    *,
    accepted: bool = True,
    ordering: OrderingPolicy = OrderingPolicy.SAFE_DEFAULT,
) -> PresentVariantPeptideHumanReviewWorkspaceRequest:
    aligned = _artifact("alignment.m1702", "8", M1705_M1702_RESULT_MEDIA_TYPE)
    model = _artifact("model.presentation", "9")
    config = PresentationConfiguration(
        configuration_id="configuration.m1705",
        version="0.1.0",
        method="deterministic review workspace ordering",
        model_reference=model,
        evidence=(_evidence("configuration.m1705", "0"),),
    )
    policy = PresentationPolicy(
        required_views=(
            ViewKind.TASK_SUMMARY,
            ViewKind.EVIDENCE_REVIEW,
            ViewKind.UNCERTAINTY,
            ViewKind.DISCREPANCY,
            ViewKind.PROVENANCE,
            ViewKind.NEXT_ACTION,
        ),
        default_ordering=ordering,
        maximum_items=16,
        configuration=config,
    )
    statuses = [ReviewItemStatus.SUPPORTED] * 6
    if scenario == "conflicted":
        statuses[3] = ReviewItemStatus.CONFLICTED
    elif scenario == "limited":
        statuses[2] = ReviewItemStatus.LIMITED
    elif scenario == "abstained":
        statuses[3] = ReviewItemStatus.ABSTAINED
    views = (
        ViewKind.TASK_SUMMARY,
        ViewKind.EVIDENCE_REVIEW,
        ViewKind.UNCERTAINTY,
        ViewKind.DISCREPANCY,
        ViewKind.PROVENANCE,
        ViewKind.NEXT_ACTION,
    )
    items = tuple(_item(index, view, statuses[index]) for index, view in enumerate(views))
    source_artifacts = (
        aligned,
        model,
        *(
        artifact
        for item in items
        for artifact in (item.evidence[0].reference, item.provenance_artifact)
        ),
    )
    context = ExecutionContext(
        request_id="request.m1705",
        actor_id="actor.synthetic",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=_controls(accepted),
    )
    return PresentVariantPeptideHumanReviewWorkspaceRequest(
        request_id="request.m1705",
        context=context,
        aligned_evidence_bundle=aligned,
        policy=policy,
        review_items=items,
        source_artifacts=source_artifacts,
    )


def run_evaluator() -> dict[str, Any]:
    engine = M1705WorkflowPresentationEngine()
    checks: list[dict[str, object]] = []
    for name, scenario, expected in (
        ("supported_workspace", "supported", "presented"),
        ("conflict_visible", "conflicted", "presented"),
        ("limited_review", "limited", "presented"),
        ("unsupported_abstention", "abstained", "abstained"),
    ):
        result = engine.infer(build_scenario_request(scenario))
        checks.append({"name": name, "passed": result.status.value == expected})
    replay = engine.infer(build_scenario_request("supported"))
    checks.append({"name": "replay", "passed": engine.verify(replay) == replay})
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1705AuthorizationError:
        denied = True
    else:
        denied = False
    checks.append({"name": "authorization_gate", "passed": denied})
    return {
        "module_id": "GLIO-PROTEOGEN-M17-05",
        "fixture": str(FIXTURE),
        "declared_cases": len(checks),
        "executed_cases": len(checks),
        "passed_cases": sum(bool(item["passed"]) for item in checks),
        "checks": checks,
        "passed": all(bool(item["passed"]) for item in checks),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_evaluator(), sort_keys=True))

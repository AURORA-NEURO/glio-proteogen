"""Synthetic evaluator for provisional M18-05 workflow presentation."""

# Synthetic metadata builders intentionally keep scenario arguments explicit.
# ruff: noqa: FBT001, FBT002, T201

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m18_05 import (
    M1805_M1804_INPUT_MEDIA_TYPE,
    PresentBiomarkerPanelReviewWorkspaceRequest,
    WorkspaceConfiguration,
    WorkspaceSection,
    WorkspaceSectionKind,
    WorkspaceStatus,
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
    SupportDecision,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c18_spatial_proteomics.m18_05_workflow_presentation_service import (
    M1805AuthorizationError,
    M1805WorkflowPresentationEngine,
)

FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m18_05" / "scenarios.json"
SECTION_COUNT = 6


def _artifact(
    name: str, digest_char: str, media: str = "application/octet-stream"
) -> ArtifactReference:
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
        claim="Synthetic caller-declared M18-05 workspace evidence.",
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


def _section(index: int, kind: WorkspaceSectionKind, source: ArtifactReference) -> WorkspaceSection:
    return WorkspaceSection(
        section_id=f"section.m1805.{index}",
        kind=kind,
        title=kind.value.replace("_", " ").title(),
        summary="Synthetic workspace section remains attributable and review-oriented.",
        source_artifacts=(source,),
        evidence=(_evidence(f"section-{index}", "abcdefgh"[index]),),
    )


def build_scenario_request(
    scenario: str = "supported",
    *,
    accepted: bool = True,
) -> PresentBiomarkerPanelReviewWorkspaceRequest:
    context = ExecutionContext(
        request_id="request.m1805",
        actor_id="actor.synthetic",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=_controls(accepted),
    )
    support = SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED
        if scenario == "unsupported"
        else SupportStatus.SUPPORTED,
        reason_code="m1805_synthetic_support",
        rationale="Synthetic support decision is caller-declared and bounded.",
    )
    upstream = _artifact("intended-use.m1804", "9", M1805_M1804_INPUT_MEDIA_TYPE)
    source = _artifact("source.workspace", "a")
    kinds = tuple(WorkspaceSectionKind)
    sections = tuple(_section(index, kind, source) for index, kind in enumerate(kinds))
    configuration = WorkspaceConfiguration(
        configuration_id="configuration.m1805",
        version="0.1.0",
        required_sections=kinds,
        automation_bias_warning=(
            "Review evidence and uncertainty before accepting any suggested next action."
        ),
        evidence=(_evidence("configuration.m1805", "b"),),
    )
    return PresentBiomarkerPanelReviewWorkspaceRequest(
        request_id="request.m1805",
        context=context,
        upstream_result=upstream,
        sections=sections,
        default_section_order=tuple(section.section_id for section in sections),
        next_actions=(
            "Review unresolved discrepancy evidence.",
            "Confirm support before promotion.",
        ),
        configuration=configuration,
        support_decision=support,
        source_artifacts=(upstream, source),
    )


def run_evaluator() -> dict[str, Any]:
    engine = M1805WorkflowPresentationEngine()
    checks: list[dict[str, object]] = []
    presented = engine.infer(build_scenario_request())
    checks.append(
        {"name": "presented_workspace", "passed": presented.status is WorkspaceStatus.PRESENTED}
    )
    unsupported = engine.infer(build_scenario_request("unsupported"))
    checks.append(
        {
            "name": "unsupported_abstention",
            "passed": unsupported.status is WorkspaceStatus.ABSTAINED,
        }
    )
    checks.append(
        {
            "name": "six_sections",
            "passed": presented.workspace is not None
            and len(presented.workspace.sections) == SECTION_COUNT,
        }
    )
    replay = engine.infer(build_scenario_request())
    checks.append({"name": "replay", "passed": engine.verify(replay) == replay})
    tampered = replay.model_copy(update={"result_digest": "sha256:" + ("a" * 64)})
    try:
        engine.verify(tampered)
    except Exception:  # noqa: BLE001
        tamper_detected = True
    else:
        tamper_detected = False
    checks.append({"name": "tamper", "passed": tamper_detected})
    try:
        engine.infer(build_scenario_request(accepted=False))
    except M1805AuthorizationError:
        denied = True
    else:
        denied = False
    checks.append({"name": "authorization_gate", "passed": denied})
    return {
        "module_id": "GLIO-PROTEOGEN-M18-05",
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

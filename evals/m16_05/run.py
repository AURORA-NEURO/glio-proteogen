"""Run the locked synthetic M16-05 workflow presentation matrix."""

# CLI evidence runner intentionally prints machine-readable JSON.
# ruff: noqa: E501, PLR2004, S101, T201, TRY003

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.modules.c16_kinophos_object_consumer.test_m16_05_engine import _request

from glio_proteogen.contracts.m16_05 import (
    WorkspaceItemStatus,
    WorkspacePresentationStatus,
    WorkspaceViewKind,
)
from glio_proteogen.contracts.m16_05.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_05_workflow_presentation_service import (
    M1605AuthorizationError,
    M1605PresentationEngine,
)

MODULE_ID = "GLIO-PROTEOGEN-M16-05"
SCENARIO_PATH = Path(__file__).parents[2] / "tests" / "fixtures" / "m16_05" / "scenarios.json"
EXPECTED_CASE_IDS = (
    "presented_workspace",
    "warning_review_required",
    "unsupported_abstention",
    "prohibited_boundary_abstention",
    "safe_default_views",
    "replay_and_tamper",
    "authorization_gate",
    "deterministic_reconstruction",
    "uncertainty_provenance_complete",
    "next_action_and_discrepancy_visibility",
)


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def evaluate() -> dict[str, object]:
    """Execute every locked fixture case and return JSON-safe evidence."""

    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(item["case_id"] for item in fixture["cases"])
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError("M16-05 fixture case IDs are not locked")
    engine = M1605PresentationEngine()
    checks: list[EvalCheck] = []

    presented = engine.present(_request())
    checks.append(
        EvalCheck(
            "presented_workspace",
            presented.status is WorkspacePresentationStatus.PRESENTED
            and presented.workspace is not None
            and presented.support_decision.status.value == "supported",
            presented.status.value,
        )
    )
    warning = engine.present(_request(label="warning"))
    checks.append(
        EvalCheck(
            "warning_review_required",
            warning.status is WorkspacePresentationStatus.REVIEW_REQUIRED
            and warning.workspace is not None
            and warning.human_review_required,
            warning.status.value,
        )
    )
    unsupported = engine.present(_request(label="unsupported"))
    checks.append(
        EvalCheck(
            "unsupported_abstention",
            unsupported.status is WorkspacePresentationStatus.ABSTAINED
            and unsupported.workspace is None
            and unsupported.abstention_reason is not None,
            unsupported.status.value,
        )
    )
    prohibited = engine.present(_request(label="kinase"))
    checks.append(
        EvalCheck(
            "prohibited_boundary_abstention",
            prohibited.status is WorkspacePresentationStatus.ABSTAINED
            and any(item.value == "upstream_unsupported" for item in prohibited.findings),
            prohibited.status.value,
        )
    )
    assert presented.workspace is not None
    kinds = {view.kind for view in presented.workspace.views}
    checks.append(
        EvalCheck(
            "safe_default_views",
            kinds == set(WorkspaceViewKind)
            and all(view.safe_default for view in presented.workspace.views)
            and all(
                item.status is WorkspaceItemStatus.AVAILABLE
                for view in presented.workspace.views
                for item in view.items
            ),
            "six required views and safe ordering",
        )
    )
    replay = engine.present(_request())
    tamper_rejected = False
    try:
        engine.verify(replay.model_copy(update={"result_digest": sha256_digest("tampered")}))
    except ValueError:
        tamper_rejected = True
    checks.append(
        EvalCheck(
            "replay_and_tamper",
            engine.verify(replay) == replay and tamper_rejected,
            "replay verified; tamper rejected",
        )
    )
    denied = False
    try:
        engine.present(_request(accepted=False))
    except M1605AuthorizationError:
        denied = True
    checks.append(EvalCheck("authorization_gate", denied, "denied controls rejected"))
    first = engine.present(_request())
    second = engine.present(_request())
    checks.append(
        EvalCheck("deterministic_reconstruction", first == second, "byte-equivalent result")
    )
    checks.append(
        EvalCheck(
            "uncertainty_provenance_complete",
            first.uncertainty.measurement.probability == 0.9
            and len(first.provenance.control_decisions) == 7
            and first.result_digest == result_payload_digest(first),
            "seven uncertainty dimensions, controls, and digest are explicit",
        )
    )
    discrepancy = engine.present(_request(label="critical"))
    assert discrepancy.workspace is not None
    discrepancy_view = next(
        view for view in discrepancy.workspace.views if view.kind is WorkspaceViewKind.DISCREPANCY
    )
    next_action_view = next(
        view for view in discrepancy.workspace.views if view.kind is WorkspaceViewKind.NEXT_ACTION
    )
    checks.append(
        EvalCheck(
            "next_action_and_discrepancy_visibility",
            discrepancy_view.items[0].status is WorkspaceItemStatus.WARNING
            and next_action_view.items[0].next_action is not None,
            "conflict and reviewer action remain visible",
        )
    )
    passed = sum(item.passed for item in checks)
    return {
        "module_id": MODULE_ID,
        "fixture": "tests/fixtures/m16_05/scenarios.json",
        "fixture_digest": sha256_digest(fixture),
        "declared_cases": len(case_ids),
        "executed_cases": len(checks),
        "passed_cases": passed,
        "total_cases": len(checks),
        "passed": passed == len(checks),
        "checks": [asdict(item) for item in checks],
    }


def main() -> int:
    argparse.ArgumentParser().parse_args()
    report = evaluate()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

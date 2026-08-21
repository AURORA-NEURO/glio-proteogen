"""Executable M20-05 evaluator matrix."""

from __future__ import annotations

import json
from typing import Any

from glio_proteogen.contracts.m20_05 import ViewKind, WorkspaceStatus
from glio_proteogen.modules.c20_biomarker_panel.m20_05_workflow_presentation_service import (
    M2005AuthorizationError,
    M2005Service,
)

from .fixture import abstained_request, build_request, conflicted_request, denied_request


def run_evaluator() -> dict[str, Any]:
    service = M2005Service()
    request = build_request()
    first = service.present(request)
    second = service.present(request)
    conflicted = service.present(conflicted_request())
    abstained = service.present(abstained_request())
    authorization_failed = False
    try:
        service.present(denied_request())
    except M2005AuthorizationError:
        authorization_failed = True
    replay = service.replay(first)
    checks = {
        "presented_workspace": (
            first.status is WorkspaceStatus.PRESENTED and first.workspace is not None
        ),
        "honors_safe_default_order": first.workspace is not None
        and tuple(item.view_kind for item in first.workspace.items)
        == (
            ViewKind.DISCREPANCY,
            ViewKind.UNCERTAINTY,
            ViewKind.EVIDENCE_REVIEW,
            ViewKind.PROVENANCE,
            ViewKind.NEXT_ACTION,
            ViewKind.TASK_SUMMARY,
        ),
        "conflict_visible": conflicted.status is WorkspaceStatus.PRESENTED
        and any(item.code.value == "discrepancy_requires_review" for item in conflicted.findings),
        "item_abstained": (
            abstained.status is WorkspaceStatus.ABSTAINED and abstained.workspace is None
        ),
        "denied_fail_closed": authorization_failed,
        "deterministic_result": first.result_digest == second.result_digest,
        "replay_verified": replay.result_digest == first.result_digest,
        "supported_status": first.support_decision.status.value == "supported",
    }
    return {
        "module": "M20-05",
        "scenario_count": len(checks),
        "passed": sum(checks.values()),
        "checks": checks,
        "fixture_request_digest": first.request_digest,
        "fixture_result_digest": first.result_digest,
    }


def main() -> None:
    print(json.dumps(run_evaluator(), sort_keys=True, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["main", "run_evaluator"]

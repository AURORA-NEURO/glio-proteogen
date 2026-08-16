"""Locked evaluator for the M19-05 workflow presentation service."""

# Synthetic scenario metadata is intentionally explicit.
# ruff: noqa: T201

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evals.m19_05.scenarios import build_request
from glio_proteogen.contracts.m19_05 import ReviewItemStatus, WorkspaceStatus
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_05_workflow_presentation_service import (  # noqa: E501
    M1905AuthorizationError,
    M1905Engine,
    M1905ReplayError,
)

FIXTURE = Path(__file__).parents[2] / "tests" / "fixtures" / "m19_05" / "scenarios.json"
_VIEW_COUNT = 6


def _fixture_digest() -> str:
    return hashlib.sha256(FIXTURE.read_bytes()).hexdigest()


def run_evaluator() -> dict[str, Any]:
    engine = M1905Engine()
    checks: list[dict[str, object]] = []

    presented = engine.present(build_request())
    checks.append(
        {
            "name": "supported_workspace",
            "passed": presented.status is WorkspaceStatus.PRESENTED
            and presented.workspace is not None
            and len(presented.workspace.items) == _VIEW_COUNT,
        }
    )

    limited = engine.present(build_request(item_status=ReviewItemStatus.LIMITED))
    checks.append(
        {
            "name": "limited_review_visible",
            "passed": limited.status is WorkspaceStatus.PRESENTED,
        }
    )

    conflicted = engine.present(build_request(item_status=ReviewItemStatus.CONFLICTED))
    checks.append(
        {
            "name": "conflicted_review_visible",
            "passed": conflicted.status is WorkspaceStatus.PRESENTED
            and any(
                item.code.value == "discrepancy_requires_review" for item in conflicted.findings
            ),
        }
    )

    abstained = engine.present(build_request(item_status=ReviewItemStatus.ABSTAINED))
    checks.append(
        {
            "name": "abstained_item",
            "passed": abstained.status is WorkspaceStatus.ABSTAINED
            and abstained.workspace is None
            and abstained.abstention_reason is not None,
        }
    )

    checks.append(
        {
            "name": "canonical_replay",
            "passed": engine.verify(presented) == presented,
        }
    )

    tampered = presented.model_copy(update={"result_digest": "sha256:" + "a" * 64})
    try:
        engine.verify(tampered)
    except M1905ReplayError:
        tamper_rejected = True
    else:
        tamper_rejected = False
    checks.append({"name": "tamper_rejection", "passed": tamper_rejected})

    try:
        engine.present(build_request(accepted=False))
    except M1905AuthorizationError:
        authorization_rejected = True
    else:
        authorization_rejected = False
    checks.append({"name": "authorization_failure", "passed": authorization_rejected})

    return {
        "module_id": "GLIO-PROTEOGEN-M19-05",
        "fixture": str(FIXTURE),
        "fixture_sha256": _fixture_digest(),
        "declared_cases": len(checks),
        "executed_cases": len(checks),
        "passed_cases": sum(bool(item["passed"]) for item in checks),
        "checks": checks,
        "passed": all(bool(item["passed"]) for item in checks),
    }


if __name__ == "__main__":
    print(json.dumps(run_evaluator(), sort_keys=True))

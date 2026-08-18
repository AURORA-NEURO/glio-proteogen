"""Verify research-only pilot evidence without requiring a package build."""

# ruff: noqa: TRY003, T201

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MODULE = "RESEARCH-PUBLIC-PROTEOMICS-PILOT"


class ResearchPilotEvidenceError(ValueError):
    """Raised when the pilot evidence receipt is incomplete or unsafe."""


def _read(evidence_root: Path, name: str) -> dict[str, Any]:
    path = evidence_root / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ResearchPilotEvidenceError(f"cannot read {path}") from error
    if not isinstance(value, dict):
        raise ResearchPilotEvidenceError(f"{path} must contain an object")
    return value


def verify(root: Path = Path()) -> dict[str, object]:
    """Verify policy, evaluation, benchmark, and scoped coverage receipts."""

    evidence_root = root / "docs/evidence/research_pilot"
    manifest = _read(evidence_root, "manifest.json")
    coverage = _read(evidence_root, "coverage.json")
    evaluation = _read(evidence_root, "evaluation.json")
    benchmark = _read(evidence_root, "benchmark.json")
    if manifest.get("module_id") != MODULE or manifest.get("no_network") is not True:
        raise ResearchPilotEvidenceError("manifest identity or network policy is invalid")
    for field in (
        "no_clinical_claims",
        "no_disease_claims",
        "no_treatment_claims",
        "owner_review_required",
        "result_digest_replay_bound",
    ):
        if manifest.get(field) is not True:
            raise ResearchPilotEvidenceError(f"manifest policy {field} is not closed")
    if (
        coverage.get("module_id") != MODULE
        or coverage.get("branch_enabled") is not True
        or coverage.get("passed") is not True
        or float(coverage.get("branch_coverage_percent", 0.0))
        < float(coverage.get("fail_under", 95.0))
    ):
        raise ResearchPilotEvidenceError("coverage evidence does not meet the gate")
    if evaluation.get("module_id") != MODULE or evaluation.get("passed") is not True:
        raise ResearchPilotEvidenceError("evaluation evidence did not pass")
    scenarios = evaluation.get("scenarios")
    if not isinstance(scenarios, dict) or scenarios.get("replay", {}).get("passed") is not True:
        raise ResearchPilotEvidenceError("replay scenario evidence is incomplete")
    if (
        benchmark.get("module_id") != MODULE
        or benchmark.get("passed") is not True
        or float(benchmark.get("mean_ns", 0)) > float(benchmark["budgets_ns"]["mean"])
        or float(benchmark.get("p95_ns", 0)) > float(benchmark["budgets_ns"]["p95"])
    ):
        raise ResearchPilotEvidenceError("benchmark evidence does not meet the budgets")
    return {
        "module_id": MODULE,
        "coverage_percent": coverage["branch_coverage_percent"],
        "tests": coverage["test_count"],
        "benchmark_mean_ns": benchmark["mean_ns"],
        "benchmark_p95_ns": benchmark["p95_ns"],
        "passed": True,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))

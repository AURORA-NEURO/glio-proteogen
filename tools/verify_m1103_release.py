"""Verify machine-readable M11-03 release evidence without executing opaque inputs."""

# Stable evidence-specific error text is intentional for this release verifier.
# TRY003 is locally disabled on the assertion sites below.
# ruff: noqa: TRY003

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_EVIDENCE = _ROOT / "release-evidence" / "m11_03"
_EXPECTED_MODULE = "GLIO-PROTEOGEN-M11-03"
_EXPECTED_FIXTURE = "m11-03-mechanistic-feature-constructor-v1"
_EXPECTED_DIGEST = "sha256:88caacf751fa63f232ab7461ab6a096bf3dbbe6297a7b6da9d98fcfb82e5000f"
_EXPECTED_CASES = (
    "supported",
    "upstream_unsupported",
    "incomplete",
    "unit_failure",
    "negative_control_failure",
    "replay_tamper",
    "denied_control",
)
_CASE_COUNT = 7
_BENCHMARK_ITERATIONS = 10


class M1103ReleaseVerificationError(ValueError):
    """Raised when release evidence is incomplete or inconsistent."""


def _load(name: str) -> dict[str, Any]:
    value = json.loads((_EVIDENCE / name).read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise M1103ReleaseVerificationError(f"{name} must contain an object")
    return value


def verify_release() -> dict[str, Any]:  # noqa: C901
    evaluation = _load("evaluation.json")
    benchmark = _load("benchmark.json")
    package = _load("package.json")
    if evaluation.get("module_id") != _EXPECTED_MODULE:
        raise M1103ReleaseVerificationError("evaluation module id mismatch")
    if (
        evaluation.get("fixture_id") != _EXPECTED_FIXTURE
        or evaluation.get("fixture_digest") != _EXPECTED_DIGEST
    ):
        raise M1103ReleaseVerificationError("fixture identity mismatch")
    if tuple(evaluation.get("declared_case_ids", ())) != _EXPECTED_CASES:
        raise M1103ReleaseVerificationError("declared evaluator cases mismatch")
    if tuple(evaluation.get("executed_case_ids", ())) != _EXPECTED_CASES:
        raise M1103ReleaseVerificationError("executed evaluator cases mismatch")
    if (
        evaluation.get("declared_cases") != _CASE_COUNT
        or evaluation.get("executed_cases") != _CASE_COUNT
        or evaluation.get("passed_cases") != _CASE_COUNT
        or evaluation.get("passed") is not True
    ):
        raise M1103ReleaseVerificationError("evaluator did not pass all cases")
    if (
        benchmark.get("module_id") != _EXPECTED_MODULE
        or benchmark.get("iterations") != _BENCHMARK_ITERATIONS
    ):
        raise M1103ReleaseVerificationError("benchmark identity mismatch")
    if (
        benchmark.get("passed") is not True
        or benchmark.get("mean_ns", 0) > benchmark.get("mean_budget_ns", 0)
        or benchmark.get("p95_ns", 0) > benchmark.get("p95_budget_ns", 0)
    ):
        raise M1103ReleaseVerificationError("benchmark budget failed")
    if package.get("module_id") != _EXPECTED_MODULE:
        raise M1103ReleaseVerificationError("package module id mismatch")
    if package.get("isolated_import", {}).get("passed") is not True:
        raise M1103ReleaseVerificationError("isolated import failed")
    coverage = package.get("coverage", {})
    if coverage.get("branch_percent", 0) < coverage.get("fail_under", 95):
        raise M1103ReleaseVerificationError("coverage failed")
    return {"module_id": _EXPECTED_MODULE, "passed": True, "fixture_digest": _EXPECTED_DIGEST}


def main() -> int:
    print(json.dumps(verify_release(), sort_keys=True))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

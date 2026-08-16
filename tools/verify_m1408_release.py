"""Verify the M14-08 release-evidence closure without network access."""

# This verifier intentionally reports protocol failures with concise diagnostics.
# ruff: noqa: PLR2004, TRY003, TRY004, T201

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final, cast

ROOT: Final = Path(__file__).parents[1]
EVIDENCE: Final = ROOT / "release-evidence" / "m14_08"
FIXTURE: Final = ROOT / "tests" / "fixtures" / "m14_08" / "scenarios.json"
EXPECTED_FIXTURE_DIGEST: Final = (
    "sha256:1c97958de1b671180da266d31750c70f319d6cb5c37c373f966f30debfbee09b"
)
EXPECTED_CASE_IDS: Final = (
    "review_ready",
    "counter_evidence_chain",
    "validation_required_abstention",
    "unresolved_link_abstention",
    "unsupported_method_abstention",
    "replay_and_tamper",
    "authorization_gate",
)
EXPECTED_CASE_COUNT: Final = 7
EXPECTED_BENCHMARK_ITERATIONS: Final = 10


def _read(name: str) -> dict[str, object]:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:  # noqa: FBT001
    if not condition:
        raise ValueError(message)


def _as_int(value: object) -> int:
    return int(cast("str | int | float", value))


def _as_float(value: object) -> float:
    return float(cast("str | int | float", value))


def verify_release() -> dict[str, object]:
    evaluation = _read("evaluation.json")
    benchmark = _read("benchmark.json")
    coverage = _read("coverage.json")
    package = _read("package.json")
    _require(FIXTURE.exists(), "M14-08 fixture is missing")
    _require(_sha256(FIXTURE) == EXPECTED_FIXTURE_DIGEST, "fixture digest mismatch")
    _require(evaluation.get("module_id") == "GLIO-PROTEOGEN-M14-08", "evaluation module mismatch")
    _require(
        evaluation.get("fixture_digest") == EXPECTED_FIXTURE_DIGEST, "evaluation fixture mismatch"
    )
    _require(
        tuple(cast("list[str]", evaluation.get("case_ids", []))) == EXPECTED_CASE_IDS,
        "evaluation cases mismatch",
    )
    _require(
        evaluation.get("declared_cases") == EXPECTED_CASE_COUNT
        and evaluation.get("executed_cases") == EXPECTED_CASE_COUNT
        and evaluation.get("passed_cases") == EXPECTED_CASE_COUNT
        and evaluation.get("passed") is True,
        "evaluation closure failed",
    )
    _require(
        benchmark.get("module_id") == "GLIO-PROTEOGEN-M14-08"
        and benchmark.get("iterations") == EXPECTED_BENCHMARK_ITERATIONS
        and benchmark.get("passed") is True
        and _as_int(benchmark.get("mean_ns", 0)) <= _as_int(benchmark.get("mean_budget_ns", 0))
        and _as_int(benchmark.get("p95_ns", 0)) <= _as_int(benchmark.get("p95_budget_ns", 0)),
        "benchmark gate failed",
    )
    _require(
        coverage.get("module_id") == "GLIO-PROTEOGEN-M14-08"
        and _as_float(coverage.get("branch_coverage_percent", 0.0))
        >= _as_float(coverage.get("fail_under_percent", 95.0))
        and coverage.get("passed") is True,
        "coverage gate failed",
    )
    _require(package.get("module_id") == "GLIO-PROTEOGEN-M14-08", "package module mismatch")
    _require(
        package.get("built") is True and package.get("isolated_import") is True,
        "package gate is incomplete",
    )
    for key in ("wheel", "sdist"):
        record = cast("dict[str, object]", package.get(key))
        _require(isinstance(record, dict), f"{key} package record missing")
        path = ROOT / str(record["path"])
        _require(path.is_file(), f"{key} artifact missing")
        _require(
            path.stat().st_size == _as_int(record["bytes"]),
            f"{key} byte count mismatch",
        )
        _require(_sha256(path) == record["sha256"], f"{key} digest mismatch")
    traceability = ROOT / "docs" / "traceability" / "GLIO-PROTEOGEN-M14-08.csv"
    _require(
        traceability.is_file() and len(traceability.read_text(encoding="utf-8").splitlines()) >= 10,
        "traceability is incomplete",
    )
    return {
        "module_id": "GLIO-PROTEOGEN-M14-08",
        "fixture_digest": EXPECTED_FIXTURE_DIGEST,
        "declared_cases": 7,
        "executed_cases": 7,
        "branch_coverage_percent": coverage["branch_coverage_percent"],
        "package_verified": True,
        "passed": True,
    }


if __name__ == "__main__":
    print(json.dumps(verify_release(), sort_keys=True))

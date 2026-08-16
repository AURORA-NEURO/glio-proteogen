"""Verify M15-06 release-evidence closure without network access."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final, cast

# ruff: noqa: PLR2004, TRY003, TRY004, T201

ROOT: Final = Path(__file__).parents[1]
EVIDENCE: Final = ROOT / "release-evidence" / "m15_06"
FIXTURE: Final = ROOT / "tests" / "fixtures" / "m15_06" / "scenarios.json"
EXPECTED_FIXTURE_DIGEST: Final = (
    "sha256:88f5a39404d259a99102057c512b1acdd76d17f9da8833a0cde528948da400f9"
)
EXPECTED_CASE_IDS: Final = (
    "simulated_bounded",
    "multi_scenario_surface",
    "input_incomplete_abstention",
    "negative_control_abstention",
    "out_of_envelope_abstention",
    "replay_and_tamper",
    "authorization_gate",
)


def _read(name: str) -> dict[str, object]:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _as_int(value: object) -> int:
    return int(cast("str | int | float", value))


def _as_float(value: object) -> float:
    return float(cast("str | int | float", value))


def _require(condition: bool, message: str) -> None:  # noqa: FBT001
    if not condition:
        raise ValueError(message)


def verify_release() -> dict[str, object]:
    evaluation = _read("evaluation.json")
    benchmark = _read("benchmark.json")
    coverage = _read("coverage.json")
    package = _read("package.json")
    _require(FIXTURE.exists(), "M15-06 fixture is missing")
    _require(_sha256(FIXTURE) == EXPECTED_FIXTURE_DIGEST, "fixture digest mismatch")
    _require(evaluation.get("module_id") == "GLIO-PROTEOGEN-M15-06", "evaluation module mismatch")
    _require(
        evaluation.get("fixture_digest") == EXPECTED_FIXTURE_DIGEST, "evaluation fixture mismatch"
    )
    _require(
        tuple(cast("list[str]", evaluation.get("case_ids", []))) == EXPECTED_CASE_IDS,
        "evaluation cases mismatch",
    )
    _require(
        evaluation.get("declared_cases") == 7
        and evaluation.get("executed_cases") == 7
        and evaluation.get("passed_cases") == 7
        and evaluation.get("passed") is True,
        "evaluation closure failed",
    )
    _require(
        benchmark.get("module_id") == "GLIO-PROTEOGEN-M15-06"
        and benchmark.get("iterations") == 10
        and benchmark.get("passed") is True
        and _as_int(benchmark.get("mean_ns", 0)) <= _as_int(benchmark.get("mean_budget_ns", 0))
        and _as_int(benchmark.get("p95_ns", 0)) <= _as_int(benchmark.get("p95_budget_ns", 0)),
        "benchmark gate failed",
    )
    _require(
        coverage.get("module_id") == "GLIO-PROTEOGEN-M15-06"
        and _as_float(coverage.get("branch_coverage_percent", 0.0)) >= 95.0
        and coverage.get("passed") is True,
        "coverage gate failed",
    )
    _require(
        package.get("module_id") == "GLIO-PROTEOGEN-M15-06"
        and package.get("built") is True
        and package.get("isolated_import") is True,
        "package gate is incomplete",
    )
    for key in ("wheel", "sdist"):
        record = cast("dict[str, object]", package.get(key))
        _require(isinstance(record, dict), f"{key} package record missing")
        path = ROOT / str(record["path"])
        _require(path.is_file(), f"{key} artifact missing")
        _require(path.stat().st_size == _as_int(record["bytes"]), f"{key} byte count mismatch")
        _require(_sha256(path) == record["sha256"], f"{key} digest mismatch")
    traceability = ROOT / "docs" / "traceability" / "GLIO-PROTEOGEN-M15-06.csv"
    _require(
        traceability.is_file() and len(traceability.read_text(encoding="utf-8").splitlines()) >= 10,
        "traceability is incomplete",
    )
    return {
        "module_id": "GLIO-PROTEOGEN-M15-06",
        "fixture_digest": EXPECTED_FIXTURE_DIGEST,
        "declared_cases": 7,
        "executed_cases": 7,
        "branch_coverage_percent": coverage["branch_coverage_percent"],
        "package_verified": True,
        "passed": True,
    }


if __name__ == "__main__":
    print(json.dumps(verify_release(), sort_keys=True))

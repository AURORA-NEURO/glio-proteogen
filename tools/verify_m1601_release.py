"""Verify M16-01 release-evidence closure without network access."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final, cast

# ruff: noqa: PLR2004, TRY003, TRY004, T201

ROOT: Final = Path(__file__).parents[1]
EVIDENCE: Final = ROOT / "release-evidence" / "m16_01"
FIXTURE: Final = ROOT / "tests" / "fixtures" / "m16_01" / "scenarios.json"
EXPECTED_FIXTURE_DIGEST: Final = (
    "sha256:917bb4a849437fc138427c4a3395098bd37ca5fc6a4463ecef29847f74e939f4"
)
EXPECTED_CASE_IDS: Final = (
    "resolved_supported",
    "version_mismatch_abstention",
    "media_mismatch_abstention",
    "missing_required_kind_abstention",
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
    _require(FIXTURE.exists(), "M16-01 fixture is missing")
    _require(_sha256(FIXTURE) == EXPECTED_FIXTURE_DIGEST, "fixture digest mismatch")
    _require(evaluation.get("module_id") == "GLIO-PROTEOGEN-M16-01", "evaluation module mismatch")
    _require(
        evaluation.get("fixture_digest") == EXPECTED_FIXTURE_DIGEST, "evaluation fixture mismatch"
    )
    _require(
        tuple(cast("list[str]", evaluation.get("case_ids", []))) == EXPECTED_CASE_IDS,
        "evaluation cases mismatch",
    )
    _require(
        evaluation.get("declared_cases") == 6
        and evaluation.get("executed_cases") == 6
        and evaluation.get("passed_cases") == 6
        and evaluation.get("passed") is True,
        "evaluation closure failed",
    )
    _require(
        benchmark.get("module_id") == "GLIO-PROTEOGEN-M16-01"
        and benchmark.get("iterations") == 10
        and benchmark.get("passed") is True
        and _as_int(benchmark.get("mean_ns", 0)) <= _as_int(benchmark.get("mean_budget_ns", 0))
        and _as_int(benchmark.get("p95_ns", 0)) <= _as_int(benchmark.get("p95_budget_ns", 0)),
        "benchmark gate failed",
    )
    _require(
        coverage.get("module_id") == "GLIO-PROTEOGEN-M16-01"
        and _as_float(coverage.get("branch_coverage_percent", 0.0)) >= 95.0
        and coverage.get("passed") is True,
        "coverage gate failed",
    )
    _require(
        package.get("module_id") == "GLIO-PROTEOGEN-M16-01"
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
    traceability = ROOT / "docs" / "traceability" / "GLIO-PROTEOGEN-M16-01.csv"
    _require(
        traceability.is_file() and len(traceability.read_text(encoding="utf-8").splitlines()) >= 10,
        "traceability is incomplete",
    )
    return {
        "module_id": "GLIO-PROTEOGEN-M16-01",
        "fixture_digest": EXPECTED_FIXTURE_DIGEST,
        "declared_cases": 6,
        "executed_cases": 6,
        "branch_coverage_percent": coverage["branch_coverage_percent"],
        "package_verified": True,
        "passed": True,
    }


if __name__ == "__main__":
    print(json.dumps(verify_release(), sort_keys=True))

"""Verify M13-03 evaluator, benchmark, coverage, and package evidence."""

# The verifier deliberately raises diagnostic exceptions and prints one CLI JSON line.
# ruff: noqa: TRY003, T201, PTH201

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Final

MODULE_ID: Final = "GLIO-PROTEOGEN-M13-03"
EXPECTED_FIXTURE_DIGEST: Final = (
    "sha256:8b90ff72b65f8b8bb9ed704039a4a78a6affc95f9b0b46b0efcab4f4f1e6c607"
)
EXPECTED_CASES: Final = (
    "supported_reference",
    "unsupported_upstream",
    "missing_evidence",
    "ood_state",
    "negative_control_failure",
    "denied_quality_control",
    "replay_tamper",
)
MIN_COVERAGE: Final = 95.0
MIN_BENCHMARK_ITERATIONS: Final = 10


class M1303ReleaseVerificationError(ValueError):
    """Raised when release evidence does not prove the M13-03 gate."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise M1303ReleaseVerificationError(f"cannot read release evidence: {path}") from exc
    if type(value) is not dict:
        raise M1303ReleaseVerificationError(f"release evidence must be an object: {path}")
    return value


def _verify_evaluation(value: dict[str, Any]) -> None:
    if value.get("module_id") != MODULE_ID:
        raise M1303ReleaseVerificationError("evaluation module id mismatch")
    if value.get("fixture_digest") != EXPECTED_FIXTURE_DIGEST:
        raise M1303ReleaseVerificationError("evaluation fixture digest mismatch")
    cases = value.get("cases")
    if (
        value.get("declared_cases") != len(EXPECTED_CASES)
        or value.get("executed_cases") != len(EXPECTED_CASES)
        or value.get("passed_cases") != len(EXPECTED_CASES)
        or value.get("all_passed") is not True
        or not isinstance(cases, list)
        or tuple(item.get("id") for item in cases) != EXPECTED_CASES
        or not all(item.get("passed") is True for item in cases)
    ):
        raise M1303ReleaseVerificationError("evaluation cases are incomplete or failed")


def _verify_benchmark(value: dict[str, Any]) -> None:
    if value.get("module_id") != MODULE_ID:
        raise M1303ReleaseVerificationError("benchmark module id mismatch")
    iterations = value.get("iterations")
    if (
        not isinstance(iterations, int)
        or isinstance(iterations, bool)
        or iterations < MIN_BENCHMARK_ITERATIONS
    ):
        raise M1303ReleaseVerificationError("benchmark must contain at least ten iterations")
    for field in ("mean_ns", "median_ns", "p95_ns", "min_ns", "max_ns"):
        if not isinstance(value.get(field), int) or value[field] < 0:
            raise M1303ReleaseVerificationError(f"benchmark field is invalid: {field}")
    if value.get("budgets_pass") is not True:
        raise M1303ReleaseVerificationError("benchmark budgets failed")
    if value["mean_ns"] > value["mean_budget_ns"] or value["p95_ns"] > value["p95_budget_ns"]:
        raise M1303ReleaseVerificationError("benchmark exceeds declared budget")


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _member_count(path: Path) -> int:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return len(archive.namelist())
    if path.suffix == ".gz":
        with tarfile.open(path, "r:gz") as archive:
            return len(archive.getnames())
    raise M1303ReleaseVerificationError(f"unsupported package suffix: {path}")


def _verify_package(value: dict[str, Any], root: Path) -> None:
    if value.get("module_id") != MODULE_ID:
        raise M1303ReleaseVerificationError("package module id mismatch")
    for kind in ("wheel", "sdist"):
        record = value.get(kind)
        if not isinstance(record, dict):
            raise M1303ReleaseVerificationError(f"missing package record: {kind}")
        path = root / str(record.get("path", ""))
        if not path.is_file():
            raise M1303ReleaseVerificationError(f"package does not exist: {kind}")
        if _digest(path) != record.get("sha256"):
            raise M1303ReleaseVerificationError(f"package digest mismatch: {kind}")
        if _member_count(path) != record.get("members"):
            raise M1303ReleaseVerificationError(f"package member count mismatch: {kind}")
    if value.get("isolated_import") is not True:
        raise M1303ReleaseVerificationError("isolated import evidence is missing")


def verify_release(root: Path = Path(".")) -> dict[str, Any]:
    """Verify all checked-in evidence and return a compact pass report."""

    evidence_root = root / "release-evidence" / "m13_03"
    evaluation = _read_json(evidence_root / "evaluation.json")
    benchmark = _read_json(evidence_root / "benchmark.json")
    package = _read_json(evidence_root / "package.json")
    _verify_evaluation(evaluation)
    _verify_benchmark(benchmark)
    _verify_package(package, root)
    coverage = package.get("coverage_percent")
    if not isinstance(coverage, (int, float)) or coverage < MIN_COVERAGE:
        raise M1303ReleaseVerificationError("branch coverage is below the release threshold")
    return {
        "module_id": MODULE_ID,
        "evaluation_passed": True,
        "benchmark_passed": True,
        "coverage_percent": coverage,
        "package_passed": True,
        "release_passed": True,
    }


def main() -> int:
    try:
        report = verify_release()
    except M1303ReleaseVerificationError as error:
        print(json.dumps({"release_passed": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

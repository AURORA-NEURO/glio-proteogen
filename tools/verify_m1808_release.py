"""Verify the reproducible M18-08 translation-monitoring release bundle."""

# ruff: noqa: TRY003

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast
from zipfile import ZipFile

if TYPE_CHECKING:
    from collections.abc import Mapping

MODULE_ID = "GLIO-PROTEOGEN-M18-08"
AUTHORITY_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_SLICE = "GLIO-PROTEOGEN_240_Module_Dossier.md:6464-6504"
FIXTURE_SHA256 = "4d94746a077427a777f234860a3e0272334745f5c55a9301293e292b3c4067fb"
SCENARIO_COUNT = 8
ADVERSARIAL_CASE_COUNT = 8
BENCHMARK_ITERATIONS = 25
MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000
FAIL_UNDER = 95.0
BRANCH_COVERAGE_FLOOR: Final = 0.90


class M1808ReleaseEvidenceError(ValueError):
    """Raised when M18-08 release evidence is incomplete or inconsistent."""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise M1808ReleaseEvidenceError(f"{label} must be an object")
    return value


def _load(path: Path, label: str) -> Mapping[str, object]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), label)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M1808ReleaseEvidenceError(f"{label} is not valid UTF-8 JSON") from error


def _require(document: Mapping[str, object], field: str, expected: object, label: str) -> None:
    if document.get(field) != expected:
        raise M1808ReleaseEvidenceError(f"{label} has unexpected {field}")


def verify_evaluation(path: Path) -> None:
    report = _load(path, "M18-08 evaluation report")
    _require(report, "module_id", MODULE_ID, "evaluation report")
    _require(report, "dossier_sha256", f"sha256:{AUTHORITY_SHA256}", "evaluation report")
    _require(report, "dossier_slice", AUTHORITY_SLICE, "evaluation report")
    _require(report, "scenario_count", SCENARIO_COUNT, "evaluation report")
    _require(report, "adversarial_case_count", ADVERSARIAL_CASE_COUNT, "evaluation report")
    _require(report, "adversarial_passed_count", ADVERSARIAL_CASE_COUNT, "evaluation report")
    if report.get("passed") is not True:
        raise M1808ReleaseEvidenceError("evaluation report did not pass")
    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        raise M1808ReleaseEvidenceError("evaluation checks must be a non-empty array")
    if any(_mapping(check, "evaluation check").get("passed") is not True for check in checks):
        raise M1808ReleaseEvidenceError("evaluation check did not pass")


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise M1808ReleaseEvidenceError(f"{field} is not numeric")
    if not math.isfinite(value) or value < 0:
        raise M1808ReleaseEvidenceError(f"{field} is invalid")
    return float(value)


def verify_benchmark(path: Path) -> None:
    report = _load(path, "M18-08 benchmark report")
    _require(report, "module_id", MODULE_ID, "benchmark report")
    _require(report, "iterations", BENCHMARK_ITERATIONS, "benchmark report")
    _require(report, "mean_budget_ns", MEAN_BUDGET_NS, "benchmark report")
    _require(report, "p95_budget_ns", P95_BUDGET_NS, "benchmark report")
    if report.get("replay_verified") is not True:
        raise M1808ReleaseEvidenceError("benchmark replay evidence is missing")
    if report.get("passed") is not True:
        raise M1808ReleaseEvidenceError("benchmark report did not pass")
    if _finite_nonnegative(report.get("mean_ns"), "benchmark mean_ns") > MEAN_BUDGET_NS:
        raise M1808ReleaseEvidenceError("benchmark exceeds mean budget")
    if _finite_nonnegative(report.get("p95_ns"), "benchmark p95_ns") > P95_BUDGET_NS:
        raise M1808ReleaseEvidenceError("benchmark exceeds p95 budget")


def verify_coverage(path: Path) -> None:
    report = _load(path, "M18-08 coverage report")
    _require(report, "module_id", MODULE_ID, "coverage report")
    if report.get("branch") is not True:
        raise M1808ReleaseEvidenceError("coverage report is not branch-enabled")
    threshold = _finite_nonnegative(report.get("fail_under"), "coverage fail_under")
    if threshold < FAIL_UNDER:
        raise M1808ReleaseEvidenceError("coverage fail-under is below policy")
    values = tuple(
        report.get(field)
        for field in ("statements", "covered_statements", "branches", "covered_branches")
    )
    if any(type(value) is not int or value < 0 for value in values):
        raise M1808ReleaseEvidenceError("coverage counts are invalid")
    statements, covered_statements, branches, covered_branches = cast(
        "tuple[int, int, int, int]", values
    )
    if covered_statements > statements or covered_branches > branches:
        raise M1808ReleaseEvidenceError("coverage counts are inconsistent")
    percent = _finite_nonnegative(report.get("percent"), "coverage percent")
    total_paths = statements + branches
    expected = (covered_statements + covered_branches) / total_paths * 100 if total_paths else 100.0
    if not math.isclose(percent, expected, rel_tol=0, abs_tol=1e-9) or percent < threshold:
        raise M1808ReleaseEvidenceError("coverage is below fail-under or inconsistent")
    if branches == 0 or covered_branches / branches < BRANCH_COVERAGE_FLOOR:
        raise M1808ReleaseEvidenceError("branch coverage is below the release floor")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_fixture(path: Path) -> None:
    if not path.is_file() or _sha256(path) != FIXTURE_SHA256:
        raise M1808ReleaseEvidenceError("fixture evidence is missing or has the wrong digest")


def _verify_file(path: Path, item: Mapping[str, object], label: str) -> None:
    if not path.is_file():
        raise M1808ReleaseEvidenceError(f"{label} is missing")
    _require(item, "filename", path.name, label)
    _require(item, "sha256", _sha256(path), label)
    _require(item, "size_bytes", path.stat().st_size, label)
    if path.suffix == ".whl":
        with ZipFile(path) as archive:
            members = len([member for member in archive.infolist() if not member.is_dir()])
        _require(item, "member_count", members, label)


def verify_package(path: Path, dist_dir: Path) -> None:
    report = _load(path, "M18-08 package report")
    _require(report, "module_id", MODULE_ID, "package report")
    wheel = _mapping(report.get("wheel"), "package wheel")
    sdist = _mapping(report.get("sdist"), "package sdist")
    wheel_name = wheel.get("filename")
    sdist_name = sdist.get("filename")
    if not isinstance(wheel_name, str) or not wheel_name.endswith(".whl"):
        raise M1808ReleaseEvidenceError("wheel filename is invalid")
    if not isinstance(sdist_name, str) or not sdist_name.endswith(".tar.gz"):
        raise M1808ReleaseEvidenceError("sdist filename is invalid")
    _verify_file(dist_dir / wheel_name, wheel, "package wheel")
    _verify_file(dist_dir / sdist_name, sdist, "package sdist")
    if report.get("isolated_import") is not True:
        raise M1808ReleaseEvidenceError("isolated import evidence is missing")


def verify_release(evidence_dir: Path, dist_dir: Path, fixture: Path) -> None:
    verify_evaluation(evidence_dir / "evaluation.json")
    verify_benchmark(evidence_dir / "benchmark.json")
    verify_coverage(evidence_dir / "coverage.json")
    verify_fixture(fixture)
    verify_package(evidence_dir / "package.json", dist_dir)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("dist", type=Path)
    parser.add_argument("fixture", type=Path)
    arguments = parser.parse_args()
    verify_release(arguments.evidence, arguments.dist, arguments.fixture)

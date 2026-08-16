"""Verify the reproducible M16-05 release evidence bundle."""

# ruff: noqa: TRY003

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZipFile

if TYPE_CHECKING:
    from collections.abc import Mapping

MODULE_ID = "GLIO-PROTEOGEN-M16-05"
FIXTURE_DIGEST = "sha256:f4a228bcde796166346f77cbfd6a1b956e150cf415d69d59f8c7b00ba85577b7"
CASE_IDS = (
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
MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000
BENCHMARK_ITERATIONS = 10
FAIL_UNDER = 95.0
AUTHORITY_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_LINES = "5612-5652"


class M1605ReleaseEvidenceError(ValueError):
    """Raised when M16-05 release evidence is incomplete or inconsistent."""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise M1605ReleaseEvidenceError(f"{label} must be an object")
    return value


def _load(path: Path, label: str) -> Mapping[str, object]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), label)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M1605ReleaseEvidenceError(f"{label} is not valid UTF-8 JSON") from error


def _require(document: Mapping[str, object], field: str, expected: object, label: str) -> None:
    if document.get(field) != expected:
        raise M1605ReleaseEvidenceError(f"{label} has unexpected {field}")


def verify_evaluation(path: Path) -> None:
    report = _load(path, "M16-05 evaluation report")
    _require(report, "module_id", MODULE_ID, "evaluation report")
    _require(report, "fixture_digest", FIXTURE_DIGEST, "evaluation report")
    for field in ("declared_cases", "executed_cases", "passed_cases", "total_cases"):
        _require(report, field, len(CASE_IDS), "evaluation report")
    if report.get("passed") is not True:
        raise M1605ReleaseEvidenceError("evaluation report did not pass")
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise M1605ReleaseEvidenceError("evaluation checks must be an array")
    names: list[str] = []
    for check in checks:
        item = _mapping(check, "evaluation check")
        name = item.get("name")
        if not isinstance(name, str):
            raise M1605ReleaseEvidenceError("evaluation check has no name")
        names.append(name)
        if item.get("passed") is not True:
            raise M1605ReleaseEvidenceError("evaluation check did not pass")
    if tuple(names) != CASE_IDS:
        raise M1605ReleaseEvidenceError("evaluation report lacks exact scenario closure")


def verify_benchmark(path: Path) -> None:
    report = _load(path, "M16-05 benchmark report")
    _require(report, "module_id", MODULE_ID, "benchmark report")
    _require(report, "iterations", BENCHMARK_ITERATIONS, "benchmark report")
    _require(report, "mean_budget_ns", MEAN_BUDGET_NS, "benchmark report")
    _require(report, "p95_budget_ns", P95_BUDGET_NS, "benchmark report")
    if report.get("passed") is not True:
        raise M1605ReleaseEvidenceError("benchmark report did not pass")
    mean_ns = report.get("mean_ns")
    p95_ns = report.get("p95_ns")
    if isinstance(mean_ns, bool) or not isinstance(mean_ns, (int, float)):
        raise M1605ReleaseEvidenceError("benchmark mean is not numeric")
    if isinstance(p95_ns, bool) or not isinstance(p95_ns, (int, float)):
        raise M1605ReleaseEvidenceError("benchmark p95 is not numeric")
    if (
        not math.isfinite(mean_ns)
        or not math.isfinite(p95_ns)
        or mean_ns < 0
        or p95_ns < 0
        or mean_ns > MEAN_BUDGET_NS
        or p95_ns > P95_BUDGET_NS
    ):
        raise M1605ReleaseEvidenceError("benchmark exceeds provisional timing budgets")


def verify_coverage(path: Path) -> None:
    report = _load(path, "M16-05 coverage report")
    _require(report, "module_id", MODULE_ID, "coverage report")
    if report.get("branch") is not True:
        raise M1605ReleaseEvidenceError("coverage report is not branch-enabled")
    percent = report.get("percent")
    threshold = report.get("fail_under")
    if isinstance(percent, bool) or not isinstance(percent, (int, float)):
        raise M1605ReleaseEvidenceError("coverage percentage is not numeric")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise M1605ReleaseEvidenceError("coverage fail-under is not numeric")
    if not math.isfinite(percent) or percent < threshold or threshold < FAIL_UNDER:
        raise M1605ReleaseEvidenceError("coverage is below fail-under")
    for field in ("statements", "covered_statements", "branches", "covered_branches"):
        value = report.get(field)
        if type(value) is not int or value < 0:
            raise M1605ReleaseEvidenceError(f"coverage {field} is invalid")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_file(path: Path, item: Mapping[str, object], label: str) -> None:
    if not path.is_file():
        raise M1605ReleaseEvidenceError(f"{label} is missing")
    _require(item, "filename", path.name, label)
    _require(item, "sha256", _sha256(path), label)
    _require(item, "size_bytes", path.stat().st_size, label)
    if path.suffix == ".whl":
        with ZipFile(path) as archive:
            members = len([member for member in archive.infolist() if not member.is_dir()])
        _require(item, "member_count", members, label)


def verify_package(path: Path, dist_dir: Path) -> None:
    report = _load(path, "M16-05 package report")
    _require(report, "module_id", MODULE_ID, "package report")
    wheel = _mapping(report.get("wheel"), "package wheel")
    sdist = _mapping(report.get("sdist"), "package sdist")
    wheel_name = wheel.get("filename")
    sdist_name = sdist.get("filename")
    if not isinstance(wheel_name, str) or not wheel_name.endswith(".whl"):
        raise M1605ReleaseEvidenceError("wheel filename is invalid")
    if not isinstance(sdist_name, str) or not sdist_name.endswith(".tar.gz"):
        raise M1605ReleaseEvidenceError("sdist filename is invalid")
    _verify_file(dist_dir / wheel_name, wheel, "package wheel")
    _verify_file(dist_dir / sdist_name, sdist, "package sdist")
    if report.get("isolated_import") is not True:
        raise M1605ReleaseEvidenceError("isolated import evidence is missing")


def verify_release(evidence_dir: Path, dist_dir: Path) -> None:
    verify_evaluation(evidence_dir / "evaluation.json")
    verify_benchmark(evidence_dir / "benchmark.json")
    verify_coverage(evidence_dir / "coverage.json")
    verify_package(evidence_dir / "package.json", dist_dir)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("dist", type=Path)
    arguments = parser.parse_args()
    verify_release(arguments.evidence, arguments.dist)

"""Verify the reproducible M13-08 release evidence bundle."""

# Evidence verification deliberately uses only the standard library.
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

MODULE_ID = "GLIO-PROTEOGEN-M13-08"
FIXTURE_DIGEST = "sha256:eb929387f8ebe0e28b2fe66e4baa0fde4e2ff35ae7a5b94fa54704551e97303e"
CASE_IDS = (
    "bayesian_dossier_ready",
    "state_space_dossier_ready",
    "mechanistic_dossier_ready",
    "unsupported_family_abstention",
    "claim_ceiling_visible",
    "replay_and_tamper",
    "authorization_gate",
)
MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000
BENCHMARK_ITERATIONS = 10
FAIL_UNDER = 95.0


class M1308ReleaseEvidenceError(ValueError):
    """Raised when M13-08 release evidence is incomplete or inconsistent."""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise M1308ReleaseEvidenceError(f"{label} must be an object")
    return value


def _load(path: Path, label: str) -> Mapping[str, object]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), label)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M1308ReleaseEvidenceError(f"{label} is not valid UTF-8 JSON") from error


def _require(document: Mapping[str, object], field: str, expected: object, label: str) -> None:
    if document.get(field) != expected:
        raise M1308ReleaseEvidenceError(f"{label} has unexpected {field}")


def verify_evaluation(path: Path) -> None:
    """Verify exact fixture identity, case closure, and all green checks."""

    report = _load(path, "M13-08 evaluation report")
    _require(report, "module_id", MODULE_ID, "evaluation report")
    _require(report, "fixture_digest", FIXTURE_DIGEST, "evaluation report")
    for field in ("declared_cases", "executed_cases", "passed_cases", "total_cases"):
        _require(report, field, len(CASE_IDS), "evaluation report")
    if report.get("passed") is not True:
        raise M1308ReleaseEvidenceError("evaluation report has unexpected passed")
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise M1308ReleaseEvidenceError("evaluation report checks must be an array")
    names: list[str] = []
    for check in checks:
        item = _mapping(check, "evaluation check")
        name = item.get("name")
        if not isinstance(name, str):
            raise M1308ReleaseEvidenceError("evaluation check has no name")
        names.append(name)
        if item.get("passed") is not True:
            raise M1308ReleaseEvidenceError("evaluation check has unexpected passed")
    if tuple(names) != CASE_IDS:
        raise M1308ReleaseEvidenceError("evaluation report lacks exact scenario closure")


def verify_benchmark(path: Path) -> None:
    """Verify iteration count and the published provisional timing budgets."""

    report = _load(path, "M13-08 benchmark report")
    _require(report, "module_id", MODULE_ID, "benchmark report")
    _require(report, "iterations", BENCHMARK_ITERATIONS, "benchmark report")
    _require(report, "mean_budget_ns", MEAN_BUDGET_NS, "benchmark report")
    _require(report, "p95_budget_ns", P95_BUDGET_NS, "benchmark report")
    if report.get("passed") is not True:
        raise M1308ReleaseEvidenceError("benchmark report has unexpected passed")
    mean = report.get("mean_ns")
    p95 = report.get("p95_ns")
    if isinstance(mean, bool) or not isinstance(mean, (int, float)):
        raise M1308ReleaseEvidenceError("benchmark mean is not numeric")
    if isinstance(p95, bool) or not isinstance(p95, int):
        raise M1308ReleaseEvidenceError("benchmark p95 is not an integer")
    if (
        not math.isfinite(mean)
        or mean < 0
        or mean > MEAN_BUDGET_NS
        or p95 < 0
        or p95 > P95_BUDGET_NS
    ):
        raise M1308ReleaseEvidenceError("benchmark exceeds provisional timing budgets")


def verify_coverage(path: Path) -> None:
    """Verify branch-enabled scoped coverage meets the release threshold."""

    report = _load(path, "M13-08 coverage report")
    _require(report, "module_id", MODULE_ID, "coverage report")
    if report.get("branch") is not True:
        raise M1308ReleaseEvidenceError("coverage report has unexpected branch mode")
    threshold = report.get("fail_under")
    percent = report.get("branch_percent")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise M1308ReleaseEvidenceError("coverage fail-under is not numeric")
    if isinstance(percent, bool) or not isinstance(percent, (int, float)):
        raise M1308ReleaseEvidenceError("coverage percentage is not numeric")
    if threshold < FAIL_UNDER or not math.isfinite(percent) or percent < threshold:
        raise M1308ReleaseEvidenceError("scoped branch coverage is below fail-under")
    for field in ("statements", "covered_statements", "branches", "covered_branches"):
        value = report.get(field)
        if type(value) is not int or value < 0:
            raise M1308ReleaseEvidenceError(f"coverage {field} is invalid")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_package_file(path: Path, item: Mapping[str, object], label: str) -> None:
    if not path.is_file():
        raise M1308ReleaseEvidenceError(f"{label} is missing")
    _require(item, "filename", path.name, label)
    _require(item, "sha256", _sha256(path), label)
    _require(item, "size_bytes", path.stat().st_size, label)
    if path.suffix == ".whl":
        try:
            with ZipFile(path) as archive:
                members = len([member for member in archive.infolist() if not member.is_dir()])
        except OSError as error:
            raise M1308ReleaseEvidenceError(f"{label} is not a readable wheel") from error
        _require(item, "member_count", members, label)


def verify_package(path: Path, dist_dir: Path) -> None:
    """Verify package hashes, sizes, archive closure, and isolated import evidence."""

    report = _load(path, "M13-08 package report")
    _require(report, "module_id", MODULE_ID, "package report")
    wheel = _mapping(report.get("wheel"), "package wheel")
    sdist = _mapping(report.get("sdist"), "package sdist")
    wheel_name = wheel.get("filename")
    sdist_name = sdist.get("filename")
    if not isinstance(wheel_name, str) or not wheel_name.endswith(".whl"):
        raise M1308ReleaseEvidenceError("package report wheel filename is invalid")
    if not isinstance(sdist_name, str) or not sdist_name.endswith(".tar.gz"):
        raise M1308ReleaseEvidenceError("package report sdist filename is invalid")
    _verify_package_file(dist_dir / wheel_name, wheel, "package wheel")
    _verify_package_file(dist_dir / sdist_name, sdist, "package sdist")
    if report.get("isolated_import") is not True:
        raise M1308ReleaseEvidenceError("package report has no isolated import")


def verify_release(evidence_dir: Path, dist_dir: Path) -> None:
    """Verify every M13-08 release-evidence document against the candidate build."""

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

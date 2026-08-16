"""Verify the reproducible M19-07 release-evidence bundle."""

# ruff: noqa: TRY003

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any
from zipfile import ZipFile

MODULE_ID = "GLIO-PROTEOGEN-M19-07"
AUTHORITY_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_LINES = "6780-6820"
SCENARIOS = 7
ADVERSARIAL = 8
MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000
FAIL_UNDER = 95.0
ADVERSARIAL_TARGET = 100.0


class M1907ReleaseEvidenceError(ValueError):
    """Raised when M19-07 release evidence is incomplete or inconsistent."""


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M1907ReleaseEvidenceError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise M1907ReleaseEvidenceError(f"{label} must be an object")
    return value


def _require(document: dict[str, Any], field: str, expected: object, label: str) -> None:
    if document.get(field) != expected:
        raise M1907ReleaseEvidenceError(f"{label} has unexpected {field}")


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise M1907ReleaseEvidenceError(f"{field} is not numeric")
    if not math.isfinite(value) or value < 0:
        raise M1907ReleaseEvidenceError(f"{field} is invalid")
    return float(value)


def verify_evaluation(path: Path) -> None:
    report = _load(path, "M19-07 evaluation report")
    _require(report, "module_id", MODULE_ID, "evaluation report")
    _require(report, "dossier_sha256", AUTHORITY_SHA256, "evaluation report")
    _require(report, "dossier_slice", AUTHORITY_LINES, "evaluation report")
    _require(report, "scenario_count", SCENARIOS, "evaluation report")
    _require(report, "adversarial_case_count", ADVERSARIAL, "evaluation report")
    _require(report, "adversarial_passed_count", ADVERSARIAL, "evaluation report")
    if report.get("passed") is not True:
        raise M1907ReleaseEvidenceError("evaluation report did not pass")
    if (
        _number(report.get("adversarial_coverage_percent"), "adversarial coverage")
        < ADVERSARIAL_TARGET
    ):
        raise M1907ReleaseEvidenceError("adversarial coverage is incomplete")
    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        raise M1907ReleaseEvidenceError("evaluation checks must be a non-empty array")
    if any(not isinstance(item, dict) or item.get("passed") is not True for item in checks):
        raise M1907ReleaseEvidenceError("evaluation check did not pass")


def verify_benchmark(path: Path) -> None:
    report = _load(path, "M19-07 benchmark report")
    _require(report, "module_id", MODULE_ID, "benchmark report")
    _require(report, "iterations", 25, "benchmark report")
    _require(report, "mean_budget_ns", MEAN_BUDGET_NS, "benchmark report")
    _require(report, "p95_budget_ns", P95_BUDGET_NS, "benchmark report")
    if report.get("passed") is not True:
        raise M1907ReleaseEvidenceError("benchmark report did not pass")
    if _number(report.get("mean_ns"), "mean_ns") > MEAN_BUDGET_NS:
        raise M1907ReleaseEvidenceError("benchmark exceeds mean budget")
    if _number(report.get("p95_ns"), "p95_ns") > P95_BUDGET_NS:
        raise M1907ReleaseEvidenceError("benchmark exceeds p95 budget")
    for field in ("request_digest", "result_digest"):
        if not isinstance(report.get(field), str) or not report[field].startswith("sha256:"):
            raise M1907ReleaseEvidenceError(f"benchmark {field} is not a digest")


def verify_coverage(path: Path) -> None:
    report = _load(path, "M19-07 coverage report")
    _require(report, "module_id", MODULE_ID, "coverage report")
    if report.get("branch") is not True:
        raise M1907ReleaseEvidenceError("coverage report is not branch-enabled")
    percent = _number(report.get("percent"), "coverage percent")
    fail_under = _number(report.get("fail_under"), "coverage fail-under")
    if percent < fail_under or fail_under < FAIL_UNDER:
        raise M1907ReleaseEvidenceError("coverage is below fail-under")
    for field in ("statements", "covered_statements", "branches", "covered_branches"):
        value = report.get(field)
        if type(value) is not int or value < 0:
            raise M1907ReleaseEvidenceError(f"coverage {field} is invalid")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_file(path: Path, item: dict[str, Any], label: str) -> None:
    if not path.is_file():
        raise M1907ReleaseEvidenceError(f"{label} is missing")
    _require(item, "filename", path.name, label)
    _require(item, "sha256", _sha256(path), label)
    _require(item, "size_bytes", path.stat().st_size, label)
    if path.suffix == ".whl":
        with ZipFile(path) as archive:
            member_count = len([entry for entry in archive.infolist() if not entry.is_dir()])
        _require(item, "member_count", member_count, label)


def verify_package(path: Path, dist_dir: Path) -> None:
    report = _load(path, "M19-07 package report")
    _require(report, "module_id", MODULE_ID, "package report")
    wheel = report.get("wheel")
    sdist = report.get("sdist")
    if not isinstance(wheel, dict) or not isinstance(sdist, dict):
        raise M1907ReleaseEvidenceError("package wheel/sdist records are required")
    wheel_name = wheel.get("filename")
    sdist_name = sdist.get("filename")
    if not isinstance(wheel_name, str) or not wheel_name.endswith(".whl"):
        raise M1907ReleaseEvidenceError("wheel filename is invalid")
    if not isinstance(sdist_name, str) or not sdist_name.endswith(".tar.gz"):
        raise M1907ReleaseEvidenceError("sdist filename is invalid")
    _verify_file(dist_dir / wheel_name, wheel, "package wheel")
    _verify_file(dist_dir / sdist_name, sdist, "package sdist")
    if report.get("isolated_import") is not True:
        raise M1907ReleaseEvidenceError("isolated import evidence is missing")


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

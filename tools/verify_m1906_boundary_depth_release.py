"""Verify the current-main M19-06 boundary-depth evidence bundle."""

# ruff: noqa: FBT003, T201, TRY003

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from zipfile import ZipFile

MODULE_ID = "GLIO-PROTEOGEN-M19-06"
AUTHORITY_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_SLICE = "GLIO-PROTEOGEN_240_Module_Dossier.md:6736-6776"
FAIL_UNDER = 95.0
EVALUATOR_COVERAGE = 100.0


class M1906BoundaryDepthEvidenceError(ValueError):
    """Raised when boundary-depth evidence is missing or inconsistent."""


def _load(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M1906BoundaryDepthEvidenceError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise M1906BoundaryDepthEvidenceError(f"{label} must be an object")
    return value


def _require(document: dict[str, object], field: str, expected: object, label: str) -> None:
    if document.get(field) != expected:
        raise M1906BoundaryDepthEvidenceError(f"{label} has unexpected {field}")


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise M1906BoundaryDepthEvidenceError(f"{field} is not numeric")
    if not math.isfinite(value) or value < 0:
        raise M1906BoundaryDepthEvidenceError(f"{field} is invalid")
    return float(value)


def verify_evaluation(path: Path) -> None:
    report = _load(path, "evaluation")
    _require(report, "module_id", MODULE_ID, "evaluation")
    _require(report, "dossier_sha256", AUTHORITY_SHA256, "evaluation")
    _require(report, "dossier_slice", AUTHORITY_SLICE, "evaluation")
    _require(report, "declared_case_count", 9, "evaluation")
    _require(report, "executed_case_count", 9, "evaluation")
    _require(report, "adversarial_case_count", 8, "evaluation")
    if (
        report.get("status") != "PASS"
        or _number(report.get("coverage_percent"), "coverage") < EVALUATOR_COVERAGE
    ):
        raise M1906BoundaryDepthEvidenceError("evaluation did not pass")
    checks = report.get("checks")
    if not isinstance(checks, list) or any(
        not isinstance(item, dict) or item.get("passed") is not True for item in checks
    ):
        raise M1906BoundaryDepthEvidenceError("evaluation contains a failed check")


def verify_benchmark(path: Path) -> None:
    report = _load(path, "benchmark")
    _require(report, "module_id", MODULE_ID, "benchmark")
    _require(report, "iterations", 25, "benchmark")
    _require(report, "passed", True, "benchmark")
    if _number(report.get("mean_ns"), "mean_ns") > _number(
        report.get("mean_budget_ns"), "mean_budget_ns"
    ):
        raise M1906BoundaryDepthEvidenceError("benchmark mean exceeds budget")
    if _number(report.get("p95_ns"), "p95_ns") > _number(
        report.get("p95_budget_ns"), "p95_budget_ns"
    ):
        raise M1906BoundaryDepthEvidenceError("benchmark p95 exceeds budget")


def verify_coverage(path: Path) -> None:
    report = _load(path, "coverage")
    meta = report.get("meta")
    totals = report.get("totals")
    if not isinstance(meta, dict) or meta.get("branch_coverage") is not True:
        raise M1906BoundaryDepthEvidenceError("coverage is not branch-enabled")
    if not isinstance(totals, dict):
        raise M1906BoundaryDepthEvidenceError("coverage totals are missing")
    if _number(totals.get("percent_covered"), "coverage percent") < FAIL_UNDER:
        raise M1906BoundaryDepthEvidenceError("coverage is below fail-under")
    for field in ("num_statements", "covered_lines", "num_branches", "covered_branches"):
        if type(totals.get(field)) is not int or totals[field] < 0:
            raise M1906BoundaryDepthEvidenceError(f"coverage {field} is invalid")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_package(path: Path, dist_dir: Path) -> None:  # noqa: C901 - receipt closure.
    report = _load(path, "package")
    _require(report, "module_id", MODULE_ID, "package")
    _require(report, "reproducible", True, "package")
    wheel = report.get("wheel")
    sdist = report.get("sdist")
    build_a = report.get("build_a")
    build_b = report.get("build_b")
    if not isinstance(wheel, dict):
        raise M1906BoundaryDepthEvidenceError("package wheel record is incomplete")
    if not isinstance(sdist, dict):
        raise M1906BoundaryDepthEvidenceError("package sdist record is incomplete")
    if not isinstance(build_a, dict):
        raise M1906BoundaryDepthEvidenceError("package build_a record is incomplete")
    if not isinstance(build_b, dict):
        raise M1906BoundaryDepthEvidenceError("package records are incomplete")
    if build_a != build_b:
        raise M1906BoundaryDepthEvidenceError("reproducible build hashes differ")
    for item in (wheel, sdist):
        filename = item.get("filename")
        if not isinstance(filename, str):
            raise M1906BoundaryDepthEvidenceError("package filename is invalid")
        artifact = dist_dir / filename
        if not artifact.is_file() or _sha256(artifact) != item.get("sha256"):
            raise M1906BoundaryDepthEvidenceError("package hash does not match artifact")
        if artifact.stat().st_size != item.get("size_bytes"):
            raise M1906BoundaryDepthEvidenceError("package size does not match artifact")
        if artifact.suffix == ".whl":
            with ZipFile(artifact) as archive:
                count = len([entry for entry in archive.infolist() if not entry.is_dir()])
            if count != item.get("member_count"):
                raise M1906BoundaryDepthEvidenceError("wheel member count does not match")
    isolated_import = report.get("isolated_import")
    if not isinstance(isolated_import, dict) or isolated_import.get("passed") is not True:
        raise M1906BoundaryDepthEvidenceError("isolated import evidence is missing")


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
    print("M19-06 boundary-depth release evidence verified")

"""Verify reproducible M26-08 evaluator, benchmark and package evidence."""

# ruff: noqa: FBT003, PLR2004, T201, TC003, TRY003

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

MODULE_ID: Final = "GLIO-PROTEOGEN-M26-08"
DOSSIER_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:9344-9384"
CASE_COUNT: Final = 10
SCHEMA_COUNT: Final = 10
ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 500_000_000
P95_BUDGET_NS: Final = 750_000_000


class M2608ReleaseVerificationError(ValueError):
    """Evidence is incomplete, mismatched or unsafe to accept."""


def _load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise M2608ReleaseVerificationError(f"cannot read evidence {path.name}") from error
    if not isinstance(value, dict):
        raise M2608ReleaseVerificationError(f"evidence {path.name} must be an object")
    return cast("dict[str, object]", value)


def _require(report: Mapping[str, object], key: str, expected: object) -> None:
    if report.get(key) != expected:
        raise M2608ReleaseVerificationError(f"{key} does not match locked M26-08 evidence")


def _fixture_digest(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise M2608ReleaseVerificationError("fixture cannot be read") from error


def verify_evaluation(evaluation: Path, fixture: Path) -> dict[str, object]:
    """Verify authority, fixture identity, case completeness and pass closure."""

    report = _load(evaluation)
    _require(report, "module_id", MODULE_ID)
    _require(report, "dossier_sha256", DOSSIER_SHA256)
    _require(report, "dossier_slice", DOSSIER_SLICE)
    _require(report, "declared_cases", CASE_COUNT)
    _require(report, "executed_cases", CASE_COUNT)
    _require(report, "passed_cases", CASE_COUNT)
    _require(report, "total_cases", CASE_COUNT)
    _require(report, "schema_count", SCHEMA_COUNT)
    _require(report, "uncertainty_dimensions", 7)
    _require(report, "passed", True)
    _require(report, "fixture_digest", _fixture_digest(fixture))
    cases = report.get("case_ids")
    if not isinstance(cases, list) or len(cases) != CASE_COUNT or len(set(cases)) != CASE_COUNT:
        raise M2608ReleaseVerificationError("evaluation case IDs are incomplete or duplicated")
    checks = report.get("checks")
    if not isinstance(checks, list) or len(checks) != CASE_COUNT:
        raise M2608ReleaseVerificationError("evaluation checks are incomplete")
    if any(not isinstance(item, dict) or item.get("passed") is not True for item in checks):
        raise M2608ReleaseVerificationError("evaluation contains a failed case")
    return report


def verify_benchmark(benchmark: Path) -> dict[str, object]:
    """Verify locked iteration count, numeric samples, budgets and pass status."""

    report = _load(benchmark)
    _require(report, "module_id", MODULE_ID)
    _require(report, "iterations", ITERATIONS)
    _require(report, "mean_budget_ns", MEAN_BUDGET_NS)
    _require(report, "p95_budget_ns", P95_BUDGET_NS)
    _require(report, "passed", True)
    samples = report.get("samples_ns")
    if not isinstance(samples, list) or len(samples) != ITERATIONS:
        raise M2608ReleaseVerificationError("benchmark samples are incomplete")
    if any(not isinstance(item, int) or item < 0 for item in samples):
        raise M2608ReleaseVerificationError("benchmark samples must be non-negative integers")
    mean = report.get("mean_ns")
    p95 = report.get("p95_ns")
    if not isinstance(mean, int) or not isinstance(p95, int):
        raise M2608ReleaseVerificationError("benchmark summary is not numeric")
    if mean > MEAN_BUDGET_NS or p95 > P95_BUDGET_NS:
        raise M2608ReleaseVerificationError("benchmark exceeds locked timing budgets")
    return report


def verify_package(package: Path) -> dict[str, object]:
    """Verify package identities, hashes, isolated import and release closure."""

    report = _load(package)
    _require(report, "module_id", MODULE_ID)
    _require(report, "isolated_import_passed", True)
    _require(report, "release_verifier_passed", True)
    for artifact in ("wheel", "sdist"):
        value = report.get(artifact)
        if not isinstance(value, dict):
            raise M2608ReleaseVerificationError(f"package {artifact} identity is missing")
        if not isinstance(value.get("filename"), str) or not value["filename"]:
            raise M2608ReleaseVerificationError(f"package {artifact} filename is missing")
        digest = value.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise M2608ReleaseVerificationError(f"package {artifact} hash is invalid")
        size = value.get("size_bytes")
        if not isinstance(size, int) or size <= 0:
            raise M2608ReleaseVerificationError(f"package {artifact} size is invalid")
    return report


def verify_release(
    evaluation: Path,
    benchmark: Path,
    package: Path,
    fixture: Path,
) -> dict[str, object]:
    """Verify all M26-08 release evidence and return a compact report."""

    verify_evaluation(evaluation, fixture)
    verify_benchmark(benchmark)
    verify_package(package)
    return {
        "module_id": MODULE_ID,
        "authority": {"dossier_sha256": DOSSIER_SHA256, "slice": DOSSIER_SLICE},
        "evaluation": str(evaluation),
        "benchmark": str(benchmark),
        "package": str(package),
        "fixture": str(fixture),
        "passed": True,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the verifier without printing artifact contents on failure."""

    values = list(arguments if arguments is not None else sys.argv[1:])
    if len(values) != 4:
        print(
            "usage: verify_m2608_release.py EVALUATION BENCHMARK PACKAGE FIXTURE", file=sys.stderr
        )
        return 2
    try:
        verify_release(*(Path(value) for value in values))
    except M2608ReleaseVerificationError as error:
        print(f"M26-08 release verification failed: {error}", file=sys.stderr)
        return 1
    print("M26-08 release verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CASE_COUNT",
    "DOSSIER_SHA256",
    "DOSSIER_SLICE",
    "ITERATIONS",
    "MEAN_BUDGET_NS",
    "MODULE_ID",
    "P95_BUDGET_NS",
    "SCHEMA_COUNT",
    "M2608ReleaseVerificationError",
    "main",
    "verify_benchmark",
    "verify_evaluation",
    "verify_package",
    "verify_release",
]

"""Verify internally consistent machine-readable M28-04 release evidence."""

# ruff: noqa: TRY003, T201

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MODULE_ID = "GLIO-PROTEOGEN-M28-04"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EVIDENCE_ROOT = Path(__file__).parents[1] / "docs" / "evidence" / "m28_04"
EXPECTED_CHECKS = 10
EXPECTED_ITERATIONS = 10
EXPECTED_FOCUSED_TESTS = 49
EXPECTED_WEIGHTED_COVERED = 1072
EXPECTED_WEIGHTED_TOTAL = 1100
EXPECTED_PACKAGE = {
    "wheel": {
        "filename": "glio_proteogen-0.1.0-py3-none-any.whl",
        "bytes": 3968347,
        "members": 2023,
        "sha256": "e551d1e6dbd62e0e24de2d89244b835f905b0e2ac5c391dcc1785fb604a21069",
    },
    "sdist": {
        "filename": "glio_proteogen-0.1.0.tar.gz",
        "bytes": 4662379,
        "members": 4741,
        "sha256": "85c483e24664628efbac638e0a481f77de09ea19c3d1c86114cfb987e28964b8",
    },
}


class M2804EvidenceError(ValueError):
    """Machine evidence is incomplete or inconsistent."""


def _load(name: str) -> dict[str, Any]:
    path = EVIDENCE_ROOT / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise M2804EvidenceError(f"unable to read {path}") from error
    if not isinstance(value, dict):
        raise M2804EvidenceError(f"{name} must contain a JSON object")
    return value


def _require(condition: bool, message: str) -> None:  # noqa: FBT001
    if not condition:
        raise M2804EvidenceError(message)


def verify() -> dict[str, Any]:
    """Verify evaluator, benchmark, coverage, package, and release records."""

    evaluation = _load("evaluation.json")
    benchmark = _load("benchmark.json")
    coverage = _load("coverage.json")
    package = _load("package.json")
    release = _load("release.json")
    records = (evaluation, benchmark, coverage, package, release)
    _require(
        all(record.get("module_id") == MODULE_ID for record in records),
        "module identity mismatch",
    )
    _require(evaluation.get("passed") is True, "evaluator did not pass")
    _require(
        evaluation.get("checks_passed") == evaluation.get("checks_declared") == EXPECTED_CHECKS,
        "evaluator matrix incomplete",
    )
    _require(benchmark.get("passed") is True, "benchmark did not pass")
    _require(
        benchmark.get("iterations") == EXPECTED_ITERATIONS,
        "benchmark iteration count mismatch",
    )
    _require(
        float(benchmark["mean_ns"]) <= int(benchmark["mean_budget_ns"])
        and int(benchmark["p95_ns"]) <= int(benchmark["p95_budget_ns"]),
        "benchmark exceeds declared budgets",
    )
    _require(
        evaluation.get("fixture_digest") == benchmark.get("request_digest"),
        "fixture digest mismatch",
    )
    _require(coverage.get("passed") is True, "coverage did not pass")
    _require(
        float(coverage["coverage_percent"]) >= float(coverage["fail_under"]),
        "coverage below fail-under",
    )
    _require(
        int(coverage["weighted_covered"]) == EXPECTED_WEIGHTED_COVERED
        and int(coverage["weighted_total"]) == EXPECTED_WEIGHTED_TOTAL,
        "coverage denominator drifted",
    )
    _require(
        release.get("focused_tests") == EXPECTED_FOCUSED_TESTS,
        "focused test count mismatch",
    )
    _require(release.get("ruff") == "passed", "Ruff did not pass")
    _require(release.get("mypy") == "passed", "MyPy did not pass")
    _require(release.get("compileall") == "passed", "compileall did not pass")
    _require(release.get("evaluator") == "10/10", "evaluator release record mismatch")
    wheel = package.get("wheel")
    sdist = package.get("sdist")
    if not isinstance(wheel, dict) or not isinstance(sdist, dict):
        raise M2804EvidenceError("package records missing")
    for label, artifact in (("wheel", wheel), ("sdist", sdist)):
        expected = EXPECTED_PACKAGE[label]
        _require(
            artifact.get("filename") == expected["filename"],
            f"{label} filename drifted",
        )
        _require(
            artifact.get("bytes") == expected["bytes"],
            f"{label} byte count drifted",
        )
        _require(
            artifact.get("members") == expected["members"],
            f"{label} member count drifted",
        )
        _require(
            SHA256_PATTERN.fullmatch(str(artifact.get("sha256", ""))) is not None,
            f"{label} hash invalid",
        )
        _require(artifact.get("sha256") == expected["sha256"], f"{label} hash drifted")
    _require(package.get("isolated_import") is True, "isolated import was not verified")
    _require(package.get("release_verifier") == "passed", "release verifier did not pass")
    artifact_audit = package.get("artifact_audit")
    if not isinstance(artifact_audit, dict):
        raise M2804EvidenceError("package artifact audit missing")
    _require(
        artifact_audit.get("generated_member_count") == 0
        and artifact_audit.get("generated_members") == [],
        "generated package members were not excluded",
    )
    _require(
        artifact_audit.get("unsafe_path_count") == 0 and artifact_audit.get("unsafe_paths") == [],
        "unsafe package paths were not excluded",
    )
    return {
        "module_id": MODULE_ID,
        "evaluator_checks": evaluation["checks_passed"],
        "benchmark_mean_ns": benchmark["mean_ns"],
        "benchmark_p95_ns": benchmark["p95_ns"],
        "coverage_percent": coverage["coverage_percent"],
        "wheel_sha256": wheel["sha256"],
        "sdist_sha256": sdist["sha256"],
        "generated_member_count": artifact_audit["generated_member_count"],
        "unsafe_path_count": artifact_audit["unsafe_path_count"],
        "passed": True,
    }


def main(argv: list[str] | None = None) -> int:
    """Print a compact verification result."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        print(json.dumps(verify(), sort_keys=True))
    except M2804EvidenceError as error:
        print(f"M28-04 evidence verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

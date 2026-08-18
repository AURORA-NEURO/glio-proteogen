"""Verify internally consistent M27-07 machine evidence."""

# ruff: noqa: PLR2004

# ruff: noqa: TRY003, T201

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MODULE_ID = "GLIO-PROTEOGEN-M27-07"
EVIDENCE_ROOT = Path(__file__).parents[1] / "docs" / "evidence" / "m27_07"
SHA256_PATTERN = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


class M2707EvidenceError(ValueError):
    """Machine evidence is incomplete or inconsistent."""


def _load(name: str) -> dict[str, Any]:
    try:
        value = json.loads((EVIDENCE_ROOT / name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise M2707EvidenceError(f"unable to read {name}") from error
    if not isinstance(value, dict):
        raise M2707EvidenceError(f"{name} must contain an object")
    return value


def _require(condition: bool, message: str) -> None:  # noqa: FBT001
    if not condition:
        raise M2707EvidenceError(message)


def verify() -> dict[str, Any]:
    evaluation = _load("evaluation.json")
    benchmark = _load("benchmark.json")
    coverage = _load("coverage.json")
    package = _load("package.json")
    release = _load("release.json")
    records = (evaluation, benchmark, coverage, package, release)
    _require(all(record.get("module_id") == MODULE_ID for record in records), "module mismatch")
    _require(evaluation.get("passed") is True, "evaluator failed")
    _require(
        evaluation.get("checks_declared") == evaluation.get("checks_passed") == 8,
        "evaluator incomplete",
    )
    _require(benchmark.get("passed") is True, "benchmark failed")
    _require(
        benchmark.get("iterations") == 10 and benchmark.get("warmup") is True,
        "benchmark shape invalid",
    )
    _require(
        int(benchmark["mean_ns"]) <= int(benchmark["mean_budget_ns"])
        and int(benchmark["p95_ns"]) <= int(benchmark["p95_budget_ns"]),
        "benchmark exceeds budget",
    )
    _require(benchmark.get("deterministic") is True, "benchmark is not deterministic")
    _require(coverage.get("passed") is True, "coverage failed")
    _require(float(coverage["coverage_percent"]) >= float(coverage["fail_under"]), "coverage low")
    _require(
        SHA256_PATTERN.fullmatch(str(evaluation.get("fixture_digest", ""))) is not None,
        "fixture digest invalid",
    )
    for label in ("wheel", "sdist"):
        artifact = package.get(label)
        if not isinstance(artifact, dict):
            raise M2707EvidenceError(f"{label} package record missing")
        _require(
            SHA256_PATTERN.fullmatch(str(artifact.get("sha256", ""))) is not None,
            f"{label} digest invalid",
        )
        _require(int(artifact.get("bytes", 0)) > 0, f"{label} size missing")
        _require(int(artifact.get("members", 0)) > 0, f"{label} members missing")
    _require(package.get("byte_identical_builds") is True, "builds differ")
    _require(package.get("isolated_import") is True, "isolated import failed")
    _require(package.get("release_verifier") == "passed", "release verifier failed")
    _require(release.get("package") == "passed", "release record package failed")
    return {
        "module_id": MODULE_ID,
        "checks": evaluation["checks_passed"],
        "coverage_percent": coverage["coverage_percent"],
        "passed": True,
    }


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        print(json.dumps(verify(), sort_keys=True))
    except M2707EvidenceError as error:
        print(f"M27-07 evidence verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

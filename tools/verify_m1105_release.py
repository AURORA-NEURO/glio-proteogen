"""Verify the machine-readable M11-05 release evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Final, cast

MODULE_ID: Final = "GLIO-PROTEOGEN-M11-05"
FIXTURE_SHA256: Final = "9600c4d00eed6920ab43dd99ec9e9fc52ed2058fc88f2b6dc1b5a171e815634f"
EXPECTED_CASES: Final = 8
MIN_BENCHMARK_ITERATIONS: Final = 10
MIN_COVERAGE_PERCENT: Final = 95.0
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")


class M1105ReleaseVerificationError(RuntimeError):
    """Release evidence is incomplete or inconsistent."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise M1105ReleaseVerificationError(  # noqa: TRY003
            f"cannot read evidence: {path}"
        ) from error
    if not isinstance(value, dict):
        raise M1105ReleaseVerificationError(  # noqa: TRY003
            f"evidence must be an object: {path}"
        )
    return cast("dict[str, object]", value)


def _require(condition: bool, message: str) -> None:  # noqa: FBT001
    if not condition:
        raise M1105ReleaseVerificationError(message)


def _verify_evaluation(root: Path) -> None:
    evidence = _json(root / "release-evidence/m11_05/evaluation.json")
    _require(evidence.get("module_id") == MODULE_ID, "evaluation module mismatch")
    _require(evidence.get("fixture_sha256") == FIXTURE_SHA256, "fixture digest mismatch")
    _require(
        evidence.get("declared_case_count")
        == evidence.get("executed_case_count")
        == evidence.get("passed_case_count")
        == EXPECTED_CASES,
        "evaluation case counts are not closed",
    )
    _require(evidence.get("passed") is True, "evaluator did not pass")
    fixture = root / "tests/fixtures/m11_05/scenarios.json"
    _require(
        hashlib.sha256(fixture.read_bytes()).hexdigest() == FIXTURE_SHA256,
        "fixture file changed",
    )


def _verify_benchmark(root: Path) -> None:
    evidence = _json(root / "release-evidence/m11_05/benchmark.json")
    _require(evidence.get("module_id") == MODULE_ID, "benchmark module mismatch")
    _require(
        cast("int", evidence.get("iterations", 0)) >= MIN_BENCHMARK_ITERATIONS,
        "benchmark iterations too low",
    )
    mean = cast("int", evidence.get("mean_ns", 0))
    p95 = cast("int", evidence.get("p95_ns", 0))
    _require(mean <= cast("int", evidence.get("mean_budget_ns", 0)), "mean budget failed")
    _require(p95 <= cast("int", evidence.get("p95_budget_ns", 0)), "p95 budget failed")
    _require(evidence.get("passed") is True, "benchmark did not pass")


def _verify_coverage(root: Path) -> None:
    evidence = _json(root / "release-evidence/m11_05/coverage.json")
    _require(evidence.get("module_id") == MODULE_ID, "coverage module mismatch")
    _require(evidence.get("branch_enabled") is True, "branch coverage is disabled")
    covered = cast("int", evidence.get("covered_branches", 0))
    branches = cast("int", evidence.get("branches", 0))
    percent = cast("float", evidence.get("branch_coverage_percent", 0.0))
    fail_under = cast("float", evidence.get("fail_under_percent", 95.0))
    _require(branches > 0 and covered == branches, "branch coverage is incomplete")
    _require(percent >= fail_under >= MIN_COVERAGE_PERCENT, "coverage gate failed")
    _require(evidence.get("passed") is True, "coverage evidence did not pass")


def _verify_package(root: Path) -> None:
    evidence = _json(root / "release-evidence/m11_05/package.json")
    _require(evidence.get("module_id") == MODULE_ID, "package module mismatch")
    for key in ("wheel", "sdist"):
        artifact = cast("dict[str, object]", evidence.get(key, {}))
        digest = cast("str", artifact.get("sha256", ""))
        _require(_SHA256_RE.fullmatch(digest) is not None, f"{key} hash missing")
        _require(cast("int", artifact.get("size_bytes", 0)) > 0, f"{key} size missing")
        _require(cast("int", artifact.get("members", 0)) > 0, f"{key} member count missing")
        _require(artifact.get("isolated_import") is True, f"{key} import gate failed")
    _require(evidence.get("build_backend") == "hatchling==1.31.0", "build backend mismatch")


def verify_release(root: Path = Path()) -> dict[str, object]:
    """Verify evaluation, benchmark, coverage and package evidence."""

    _verify_evaluation(root)
    _verify_benchmark(root)
    _verify_coverage(root)
    _verify_package(root)
    return {"module_id": MODULE_ID, "passed": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path())
    arguments = parser.parse_args(argv)
    try:
        result = verify_release(arguments.root)
    except M1105ReleaseVerificationError as error:
        sys.stderr.write(f"M11-05 release verification failed: {error}\n")
        return 1
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0


__all__ = ["M1105ReleaseVerificationError", "main", "verify_release"]


if __name__ == "__main__":
    raise SystemExit(main())

"""Verify M13-07 release evidence, fixture binding, and optional artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Final, NoReturn, cast

_MODULE_ID: Final = "GLIO-PROTEOGEN-M13-07"
_FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "m13_07" / "scenarios.json"
_EVIDENCE = Path(__file__).parents[1] / "release-evidence" / "m13_07"
_CASE_IDS: Final = (
    "supported",
    "failed_control",
    "not_evaluable",
    "unresolved_conflict",
    "denied_upstream",
    "replay_tamper",
)
_MIN_COVERAGE: Final = 95
_HASH_LENGTH: Final = 64
_ERRORS: Final = {
    "read": "cannot read release evidence",
    "object": "release evidence must contain an object",
    "evaluation_module": "evaluation module id mismatch",
    "evaluation_fixture": "evaluation fixture digest mismatch",
    "evaluation_cases": "evaluation case catalogue mismatch",
    "evaluation_matrix": "evaluation matrix is incomplete",
    "coverage": "branch coverage is below the release gate",
    "benchmark_module": "benchmark module id mismatch",
    "benchmark_values": "benchmark values must be integers",
    "benchmark_budget": "benchmark exceeds provisional budget",
    "benchmark_gate": "benchmark did not report a passing budget gate",
    "package_module": "package module id mismatch",
    "package_artifacts": "package artifact evidence is incomplete",
    "isolated_import": "isolated import did not pass",
    "hash": "package hash is invalid",
    "members": "package member count is invalid",
    "missing": "declared package artifact is missing",
    "artifact": "package artifact hash or size mismatch",
    "member_mismatch": "package artifact member count mismatch",
}


class M1307ReleaseVerificationError(ValueError):
    """Raised when release evidence does not close the M13-07 gate."""

    def __init__(self, code: str) -> None:
        super().__init__(_ERRORS[code])


def _fail(code: str) -> NoReturn:
    raise M1307ReleaseVerificationError(code)


def _read(name: str) -> dict[str, object]:
    path = _EVIDENCE / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise M1307ReleaseVerificationError("read") from error
    if not isinstance(value, dict):
        _fail("object")
    return value


def _fixture_digest() -> str:
    return f"sha256:{hashlib.sha256(_FIXTURE.read_bytes()).hexdigest()}"


def _verify_evaluation(evidence: dict[str, object]) -> None:
    if evidence.get("module_id") != _MODULE_ID:
        _fail("evaluation_module")
    if evidence.get("fixture_digest") != _fixture_digest():
        _fail("evaluation_fixture")
    case_ids = evidence.get("case_ids")
    if not isinstance(case_ids, list) or tuple(case_ids) != _CASE_IDS:
        _fail("evaluation_cases")
    if (
        evidence.get("declared_cases") != len(_CASE_IDS)
        or evidence.get("executed_cases") != len(_CASE_IDS)
        or evidence.get("passed_cases") != len(_CASE_IDS)
        or evidence.get("all_passed") is not True
    ):
        _fail("evaluation_matrix")
    coverage = evidence.get("branch_coverage_percent")
    if not isinstance(coverage, (int, float)) or coverage < _MIN_COVERAGE:
        _fail("coverage")


def _verify_benchmark(evidence: dict[str, object]) -> None:
    if evidence.get("module_id") != _MODULE_ID:
        _fail("benchmark_module")
    mean = evidence.get("mean_ns")
    p95 = evidence.get("p95_ns")
    mean_budget = evidence.get("mean_budget_ns")
    p95_budget = evidence.get("p95_budget_ns")
    if not all(isinstance(value, int) for value in (mean, p95, mean_budget, p95_budget)):
        _fail("benchmark_values")
    mean_value = cast("int", mean)
    p95_value = cast("int", p95)
    mean_budget_value = cast("int", mean_budget)
    p95_budget_value = cast("int", p95_budget)
    if (
        mean_value < 0
        or p95_value < 0
        or mean_value > mean_budget_value
        or p95_value > p95_budget_value
    ):
        _fail("benchmark_budget")
    if evidence.get("within_budget") is not True:
        _fail("benchmark_gate")


def _verify_artifact(
    artifact: dict[str, object],
    path: Path | None,
    *,
    is_wheel: bool,
) -> None:
    digest = artifact.get("sha256")
    members_evidence = artifact.get("members")
    size_evidence = artifact.get("bytes")
    if not isinstance(digest, str) or len(digest) != _HASH_LENGTH:
        _fail("hash")
    if not isinstance(members_evidence, int) or members_evidence < 1:
        _fail("members")
    if not isinstance(size_evidence, int) or size_evidence < 1:
        _fail("members")
    if path is None:
        return
    if not path.is_file():
        _fail("missing")
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_hash != digest or path.stat().st_size != size_evidence:
        _fail("artifact")
    if is_wheel:
        with zipfile.ZipFile(path) as archive:
            members = len(archive.namelist())
    else:
        with tarfile.open(path) as archive:
            members = len(archive.getnames())
    if members != members_evidence:
        _fail("member_mismatch")


def _verify_package(
    evidence: dict[str, object],
    wheel: Path | None,
    sdist: Path | None,
) -> None:
    if evidence.get("module_id") != _MODULE_ID:
        _fail("package_module")
    wheel_evidence = evidence.get("wheel")
    sdist_evidence = evidence.get("sdist")
    if not isinstance(wheel_evidence, dict) or not isinstance(sdist_evidence, dict):
        _fail("package_artifacts")
    isolated = evidence.get("isolated_import")
    if not isinstance(isolated, dict) or isolated.get("passed") is not True:
        _fail("isolated_import")
    _verify_artifact(wheel_evidence, wheel, is_wheel=True)
    _verify_artifact(sdist_evidence, sdist, is_wheel=False)


def verify_release(*, wheel: Path | None = None, sdist: Path | None = None) -> dict[str, object]:
    """Verify all committed M13-07 evidence and optional built artifacts."""

    evaluation = _read("evaluation.json")
    benchmark = _read("benchmark.json")
    package = _read("package.json")
    _verify_evaluation(evaluation)
    _verify_benchmark(benchmark)
    _verify_package(package, wheel, sdist)
    return {
        "module_id": _MODULE_ID,
        "evaluation": True,
        "benchmark": True,
        "package": True,
        "artifact_checks": wheel is not None or sdist is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--sdist", type=Path)
    args = parser.parse_args()
    try:
        report = verify_release(wheel=args.wheel, sdist=args.sdist)
    except M1307ReleaseVerificationError as error:
        sys.stderr.write(f"M13-07 release verification failed: {error}\n")
        return 1
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["M1307ReleaseVerificationError", "verify_release"]

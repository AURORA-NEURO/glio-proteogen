"""Verify M12-07 evaluator, benchmark, coverage and package evidence."""

from __future__ import annotations

import argparse
import hashlib
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Final, NoReturn, cast

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.strict_json import strict_json_loads

MODULE_ID: Final = "GLIO-PROTEOGEN-M12-07"
EVIDENCE_ROOT: Final = Path(__file__).parents[1] / "release-evidence" / "m12_07"
FIXTURE_PATH: Final = Path(__file__).parents[1] / "tests" / "fixtures" / "m12_07" / "scenarios.json"
EXPECTED_CASE_IDS: Final = (
    "supported_high",
    "failed_control",
    "missing_observation",
    "direction_mismatch",
    "unresolved_conflict",
    "denied_quality_gate",
    "abstained_control",
    "replay_tamper",
)
EXPECTED_CASE_COUNT: Final = len(EXPECTED_CASE_IDS)


class M1207ReleaseVerificationError(ValueError):
    """Raised when locked M12-07 release evidence is inconsistent."""


def _fail(message: str) -> NoReturn:
    raise M1207ReleaseVerificationError(message)


def _load(path: Path) -> dict[str, Any]:
    try:
        return cast("dict[str, Any]", strict_json_loads(path.read_bytes()))
    except (OSError, ValueError, TypeError) as exc:
        raise M1207ReleaseVerificationError(  # noqa: TRY003
            f"invalid release evidence: {path.name}"
        ) from exc


def _verify_evaluation() -> None:
    evidence = _load(EVIDENCE_ROOT / "evaluation.json")
    corpus = _load(FIXTURE_PATH)
    fixture_digest = sha256_digest(corpus)
    scenarios = cast("list[dict[str, Any]]", corpus["scenarios"])
    fixture_ids = tuple(str(item["case_id"]) for item in scenarios)
    if evidence.get("module_id") != MODULE_ID:
        _fail("evaluation module id mismatch")
    if evidence.get("fixture_digest") != fixture_digest:
        _fail("evaluation fixture digest mismatch")
    if tuple(evidence.get("declared_case_ids", ())) != EXPECTED_CASE_IDS:
        _fail("evaluation declared case IDs mismatch")
    if fixture_ids != EXPECTED_CASE_IDS:
        _fail("fixture case IDs mismatch")
    if tuple(evidence.get("executed_case_ids", ())) != EXPECTED_CASE_IDS:
        _fail("evaluation executed case IDs mismatch")
    if (
        evidence.get("declared_count") != EXPECTED_CASE_COUNT
        or evidence.get("executed_count") != EXPECTED_CASE_COUNT
    ):
        _fail("evaluation counts are not 8/8")
    if evidence.get("passed_count") != EXPECTED_CASE_COUNT or evidence.get("passed") is not True:
        _fail("evaluation did not pass all cases")
    checks = cast("list[dict[str, Any]]", evidence.get("checks", []))
    if len(checks) != EXPECTED_CASE_COUNT or not all(item.get("passed") is True for item in checks):
        _fail("evaluation check matrix is incomplete")


def _verify_benchmark() -> None:
    evidence = _load(EVIDENCE_ROOT / "benchmark.json")
    if evidence.get("module_id") != MODULE_ID or evidence.get("passed") is not True:
        _fail("benchmark did not pass")
    if evidence.get("iterations", 0) < 1:
        _fail("benchmark iteration count is invalid")
    if evidence["mean_ns"] > evidence["mean_budget_ns"]:
        _fail("benchmark mean exceeded budget")
    if evidence["p95_ns"] > evidence["p95_budget_ns"]:
        _fail("benchmark p95 exceeded budget")


def _artifact_info(path: Path) -> tuple[int, str, int]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as archive:
            members = len(archive.namelist())
    else:
        with tarfile.open(path, "r:*") as archive:
            members = len(archive.getnames())
    return path.stat().st_size, digest, members


def _verify_package(dist_dir: Path | None) -> None:
    evidence = _load(EVIDENCE_ROOT / "package.json")
    if evidence.get("module_id") != MODULE_ID:
        _fail("package module id mismatch")
    coverage = cast("dict[str, Any]", evidence.get("scoped_coverage", {}))
    if coverage.get("branch_percent", 0.0) < coverage.get("floor_percent", 95.0):
        _fail("scoped branch coverage is below release floor")
    if evidence.get("isolated_import") is not True:
        _fail("isolated import evidence is missing")
    if dist_dir is None:
        return
    for kind in ("wheel", "sdist"):
        artifact = cast("dict[str, Any]", evidence[kind])
        path = dist_dir / str(artifact["filename"])
        if not path.is_file():
            _fail(f"missing package artifact: {artifact['filename']}")
        size, digest, members = _artifact_info(path)
        if (size, digest, members) != (
            artifact["size_bytes"],
            artifact["sha256"],
            artifact["members"],
        ):
            _fail(f"package artifact evidence mismatch: {kind}")


def verify_release(dist_dir: Path | None = None) -> None:
    _verify_evaluation()
    _verify_benchmark()
    _verify_package(dist_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path)
    args = parser.parse_args(argv)
    verify_release(args.dist_dir)
    sys.stdout.write("M12-07 release verification passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

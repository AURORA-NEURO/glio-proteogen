"""Verify M10-03 evaluation, benchmark, coverage, and package evidence."""
# ruff: noqa: PLR2004, T201, TRY003

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

MODULE_ID = "GLIO-PROTEOGEN-M10-03"
CONTRACT_VERSION = "0.1.0-provisional"
EVIDENCE_ROOT = Path("release-evidence") / "M10-03"
FIXTURE = Path("tests") / "fixtures" / "m10_03" / "scenarios.json"
MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000
MIN_COVERAGE = 95.0


class M1003ReleaseVerificationError(ValueError):
    """Raised when release evidence is incomplete or internally inconsistent."""


def _load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise M1003ReleaseVerificationError(f"cannot read JSON evidence: {path}") from error
    if not isinstance(value, dict):
        raise M1003ReleaseVerificationError(f"evidence must be a JSON object: {path}")
    return value


def _require(mapping: dict[str, object], key: str) -> object:
    if key not in mapping:
        raise M1003ReleaseVerificationError(f"missing evidence field: {key}")
    return mapping[key]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fixture_case_ids(path: Path) -> tuple[str, ...]:
    document = _load(path)
    if document.get("module") != MODULE_ID or document.get("contractVersion") != CONTRACT_VERSION:
        raise M1003ReleaseVerificationError("fixture module/version mismatch")
    cases = _require(document, "cases")
    if not isinstance(cases, list):
        raise M1003ReleaseVerificationError("fixture cases must be a list")
    identifiers: list[str] = []
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise M1003ReleaseVerificationError("fixture case ids must be strings")
        identifiers.append(case["id"])
    if len(set(identifiers)) != len(identifiers):
        raise M1003ReleaseVerificationError("fixture case ids must be unique")
    return tuple(identifiers)


def _verify_evaluation(root: Path) -> None:
    evidence = _load(root / EVIDENCE_ROOT / "evaluation.json")
    if evidence.get("module") != MODULE_ID or evidence.get("contract_version") != CONTRACT_VERSION:
        raise M1003ReleaseVerificationError("evaluation module/version mismatch")
    fixture = root / FIXTURE
    expected_digest = "sha256:" + _sha256(fixture)
    if evidence.get("fixture_digest") != expected_digest:
        raise M1003ReleaseVerificationError("evaluation fixture digest mismatch")
    expected_ids = _fixture_case_ids(fixture)
    declared_value = _require(evidence, "declared_case_ids")
    executed_value = _require(evidence, "executed_case_ids")
    if not isinstance(declared_value, list) or not isinstance(executed_value, list):
        raise M1003ReleaseVerificationError("evaluation case ids must be lists")
    declared = tuple(declared_value)
    executed = tuple(executed_value)
    if declared != expected_ids or executed != expected_ids:
        raise M1003ReleaseVerificationError("evaluation case ids do not match fixture")
    if (
        evidence.get("declared_cases") != len(expected_ids)
        or evidence.get("executed_cases") != len(expected_ids)
        or evidence.get("passed") is not True
    ):
        raise M1003ReleaseVerificationError("evaluation did not pass all fixture cases")


def _verify_benchmark(root: Path) -> None:
    evidence = _load(root / EVIDENCE_ROOT / "benchmark.json")
    mean_value = _require(evidence, "mean_ns")
    p95_value = _require(evidence, "p95_ns")
    if (
        evidence.get("module_id") != MODULE_ID
        or evidence.get("contract_version") != CONTRACT_VERSION
    ):
        raise M1003ReleaseVerificationError("benchmark module/version mismatch")
    if (
        evidence.get("iterations") != 10
        or evidence.get("deterministic") is not True
        or evidence.get("passed") is not True
        or evidence.get("mean_budget_ns") != MEAN_BUDGET_NS
        or evidence.get("p95_budget_ns") != P95_BUDGET_NS
        or not isinstance(mean_value, (int, float))
        or not isinstance(p95_value, int)
        or float(mean_value) > MEAN_BUDGET_NS
        or p95_value > P95_BUDGET_NS
    ):
        raise M1003ReleaseVerificationError("benchmark evidence failed its provisional budgets")


def _verify_coverage(root: Path) -> None:
    evidence = _load(root / EVIDENCE_ROOT / "coverage.json")
    percent = _require(evidence, "percent")
    if evidence.get("branch") is not True or not isinstance(percent, (int, float)):
        raise M1003ReleaseVerificationError("scoped branch coverage is below 95 percent")
    if float(percent) < MIN_COVERAGE:
        raise M1003ReleaseVerificationError("scoped branch coverage is below 95 percent")


def _archive_members(path: Path) -> int:
    if path.suffix == ".whl":
        with ZipFile(path) as archive:
            return len(archive.namelist())
    with tarfile.open(path, "r:gz") as archive:
        return len(archive.getnames())


def _verify_package(root: Path) -> None:
    evidence = _load(root / EVIDENCE_ROOT / "package.json")
    for archive_key in ("wheel", "sdist"):
        archive = _require(evidence, archive_key)
        if not isinstance(archive, dict):
            raise M1003ReleaseVerificationError(f"package {archive_key} evidence must be an object")
        path = root / "dist-m10-03" / str(_require(archive, "filename"))
        if not path.is_file():
            raise M1003ReleaseVerificationError(f"missing package artifact: {path}")
        if _sha256(path) != _require(archive, "sha256"):
            raise M1003ReleaseVerificationError(f"package {archive_key} digest mismatch")
        if path.stat().st_size != _require(archive, "size_bytes"):
            raise M1003ReleaseVerificationError(f"package {archive_key} size mismatch")
        if _archive_members(path) != _require(archive, "members"):
            raise M1003ReleaseVerificationError(f"package {archive_key} member count mismatch")
    if evidence.get("isolated_import") is not True:
        raise M1003ReleaseVerificationError("isolated wheel import was not verified")


def verify_release(root: Path = Path()) -> dict[str, object]:
    """Validate every M10-03 release evidence receipt."""

    _verify_evaluation(root)
    _verify_benchmark(root)
    _verify_coverage(root)
    _verify_package(root)
    return {"module": MODULE_ID, "verified": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path())
    arguments = parser.parse_args(argv)
    try:
        json.dump(verify_release(arguments.root), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    except M1003ReleaseVerificationError as error:
        print(f"M10-03 release verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

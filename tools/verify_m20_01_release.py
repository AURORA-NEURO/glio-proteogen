# ruff: noqa: C901, FBT003, PLR0912, PLR0915, PLR2004, T201, TRY003
"""Verify M20-01 evaluation, benchmark, coverage, and package evidence.

This verifier intentionally uses only the Python standard library so it can run
in a clean release environment. It checks evidence consistency; it does not
promote a provisional ABI or replace human review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

MODULE_ID = "GLIO-PROTEOGEN-M20-01"
AUTHORITY_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_SLICE = "6876-6916"
MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000
MIN_COVERAGE = 95.0


class ReleaseEvidenceError(ValueError):
    """Raised when M20-01 evidence is missing, malformed, or inconsistent."""


def _load(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseEvidenceError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ReleaseEvidenceError(f"{label} must be a JSON object")
    return payload


def _require(document: dict[str, object], key: str, expected: object, label: str) -> None:
    if document.get(key) != expected:
        raise ReleaseEvidenceError(f"{label} has unexpected {key}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ReleaseEvidenceError(f"cannot read release artifact {path}") from error
    return digest.hexdigest()


def verify_release(evidence_dir: Path, wheel: Path, sdist: Path) -> None:
    evaluation = _load(evidence_dir / "evaluation.json", "evaluation evidence")
    benchmark = _load(evidence_dir / "benchmark.json", "benchmark evidence")
    coverage = _load(evidence_dir / "coverage.json", "coverage evidence")
    package = _load(evidence_dir / "package.json", "package evidence")

    for label, document in (
        ("evaluation evidence", evaluation),
        ("benchmark evidence", benchmark),
        ("package evidence", package),
    ):
        _require(document, "module_id", MODULE_ID, label)
    _require(evaluation, "dossier_sha256", AUTHORITY_SHA256, "evaluation evidence")
    _require(evaluation, "dossier_slice", AUTHORITY_SLICE, "evaluation evidence")
    _require(evaluation, "passed", True, "evaluation evidence")
    _require(evaluation, "scenario_count", 8, "evaluation evidence")
    _require(evaluation, "adversarial_passed_count", 8, "evaluation evidence")
    if evaluation.get("adversarial_coverage_percent") != 100.0:
        raise ReleaseEvidenceError("evaluation evidence lacks complete adversarial coverage")

    _require(benchmark, "passed", True, "benchmark evidence")
    _require(benchmark, "iterations", 10, "benchmark evidence")
    _require(benchmark, "warmup_count", 1, "benchmark evidence")
    _require(benchmark, "mean_budget_ns", MEAN_BUDGET_NS, "benchmark evidence")
    _require(benchmark, "p95_budget_ns", P95_BUDGET_NS, "benchmark evidence")
    mean = benchmark.get("mean_ns")
    p95 = benchmark.get("p95_ns")
    if not isinstance(mean, (int, float)) or isinstance(mean, bool) or mean > MEAN_BUDGET_NS:
        raise ReleaseEvidenceError("benchmark mean exceeds declared budget")
    if not isinstance(p95, int) or p95 > P95_BUDGET_NS:
        raise ReleaseEvidenceError("benchmark p95 exceeds declared budget")

    meta = coverage.get("meta")
    totals = coverage.get("totals")
    if not isinstance(meta, dict) or meta.get("branch_coverage") is not True:
        raise ReleaseEvidenceError("coverage evidence is not branch-enabled")
    if not isinstance(totals, dict):
        raise ReleaseEvidenceError("coverage evidence lacks totals")
    percent = totals.get("percent_covered")
    if not isinstance(percent, (int, float)) or isinstance(percent, bool) or percent < MIN_COVERAGE:
        raise ReleaseEvidenceError("scoped coverage is below the release gate")

    wheel_record = package.get("wheel")
    sdist_record = package.get("sdist")
    if not isinstance(wheel_record, dict) or not isinstance(sdist_record, dict):
        raise ReleaseEvidenceError("package evidence lacks wheel or sdist records")
    if wheel.name != wheel_record.get("filename") or sdist.name != sdist_record.get("filename"):
        raise ReleaseEvidenceError("package evidence filenames do not match artifacts")
    if wheel.stat().st_size != wheel_record.get("size_bytes") or _sha256(wheel) != wheel_record.get(
        "sha256"
    ):
        raise ReleaseEvidenceError("wheel hash or size does not match package evidence")
    if sdist.stat().st_size != sdist_record.get("size_bytes") or _sha256(sdist) != sdist_record.get(
        "sha256"
    ):
        raise ReleaseEvidenceError("sdist hash or size does not match package evidence")
    try:
        with ZipFile(wheel) as archive:
            member_count = len(archive.namelist())
    except (BadZipFile, OSError) as error:
        raise ReleaseEvidenceError("wheel cannot be opened") from error
    if member_count != wheel_record.get("member_count"):
        raise ReleaseEvidenceError("wheel member count does not match package evidence")
    if package.get("isolated_import") is not True:
        raise ReleaseEvidenceError("isolated import evidence did not pass")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        verify_release(args.evidence_dir, args.wheel, args.sdist)
    except ReleaseEvidenceError as error:
        print(f"M20-01 release verification failed: {error}", file=sys.stderr)
        return 1
    print("M20-01 release evidence verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

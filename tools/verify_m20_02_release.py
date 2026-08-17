# ruff: noqa: C901, FBT003, PLR0912, PLR0915, PLR2004, T201, TRY003
"""Verify M20-02 evaluator, benchmark, coverage, and package evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile

MODULE_ID = "GLIO-PROTEOGEN-M20-02"
AUTHORITY_SHA256 = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
AUTHORITY_SLICE = "6920-6960"
MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000
MIN_COVERAGE = 95.0


class ReleaseEvidenceError(ValueError):
    """Raised when M20-02 evidence is missing or inconsistent."""


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


def verify_reproducibility(path: Path, package: dict[str, object]) -> None:
    """Verify byte-identical wheel and sdist rebuild evidence."""

    report = _load(path, "reproducibility evidence")
    _require(report, "module_id", MODULE_ID, "reproducibility evidence")
    _require(report, "contract_version", "0.1.0-provisional", "reproducibility evidence")
    _require(
        report,
        "source_commit",
        "5a881ea4",
        "reproducibility evidence",
    )
    _require(report, "build_backend", "hatchling 1.31.0", "reproducibility evidence")
    _require(report, "build_root_policy", "outside-source-tree", "reproducibility evidence")
    for artifact_name in ("wheel", "sdist"):
        record = report.get(artifact_name)
        expected = package.get(artifact_name)
        if not isinstance(record, dict) or not isinstance(expected, dict):
            raise ReleaseEvidenceError(f"{artifact_name} reproducibility record is incomplete")
        if record.get("rebuild_count") != 2 or record.get("byte_identical") is not True:
            raise ReleaseEvidenceError(f"{artifact_name} rebuilds are not byte-identical")
        sizes = record.get("size_bytes")
        hashes = record.get("sha256")
        if (
            not isinstance(sizes, list)
            or len(sizes) != 2
            or any(type(value) is not int for value in sizes)
        ):
            raise ReleaseEvidenceError(f"{artifact_name} rebuild sizes are invalid")
        if (
            not isinstance(hashes, list)
            or len(hashes) != 2
            or any(not isinstance(value, str) for value in hashes)
        ):
            raise ReleaseEvidenceError(f"{artifact_name} rebuild hashes are invalid")
        if any(value != sizes[0] for value in sizes) or sizes[0] != expected.get("size_bytes"):
            raise ReleaseEvidenceError(f"{artifact_name} rebuild sizes disagree")
        if any(value != hashes[0] for value in hashes) or hashes[0] != expected.get("sha256"):
            raise ReleaseEvidenceError(f"{artifact_name} rebuild hashes disagree")


def verify_sdist_evidence_boundary(sdist: Path) -> None:
    """Ensure mutable release records cannot become self-referential sdist inputs."""

    if not sdist.is_file():
        raise ReleaseEvidenceError("sdist artifact is missing")
    with tarfile.open(sdist, mode="r:gz") as archive:
        names = tuple(archive.getnames())
    forbidden = (
        "/docs/evidence/M20-02.md",
        "/docs/evidence/m20_02/",
    )
    if any(any(name.endswith(path) or path in name for path in forbidden) for name in names):
        raise ReleaseEvidenceError("sdist includes mutable M20-02 release evidence")


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
    verify_reproducibility(evidence_dir / "reproducibility.json", package)
    _require(evaluation, "dossier_sha256", AUTHORITY_SHA256, "evaluation evidence")
    _require(evaluation, "dossier_slice", AUTHORITY_SLICE, "evaluation evidence")
    _require(evaluation, "passed", True, "evaluation evidence")
    _require(evaluation, "scenario_count", 3, "evaluation evidence")
    _require(evaluation, "adversarial_passed_count", 6, "evaluation evidence")
    if evaluation.get("adversarial_coverage_percent") != 100.0:
        raise ReleaseEvidenceError("evaluation evidence lacks complete adversarial coverage")
    _require(benchmark, "passed", True, "benchmark evidence")
    _require(benchmark, "iterations", 10, "benchmark evidence")
    _require(benchmark, "mean_budget_ns", MEAN_BUDGET_NS, "benchmark evidence")
    _require(benchmark, "p95_budget_ns", P95_BUDGET_NS, "benchmark evidence")
    mean = benchmark.get("mean_ns")
    p95 = benchmark.get("p95_ns")
    if not isinstance(mean, (int, float)) or isinstance(mean, bool) or mean > MEAN_BUDGET_NS:
        raise ReleaseEvidenceError("benchmark mean exceeds declared budget")
    if not isinstance(p95, (int, float)) or isinstance(p95, bool) or p95 > P95_BUDGET_NS:
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
    verify_sdist_evidence_boundary(sdist)
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
        print(f"M20-02 release verification failed: {error}", file=sys.stderr)
        return 1
    print("M20-02 release evidence verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

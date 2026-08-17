"""Verify reproducible M05-08 package and evidence receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Final

MODULE_ID: Final = "GLIO-PROTEOGEN-M05-08"
WHEEL_SHA256: Final = "92957e9e8b841f8381d4600f1dfb02e1fbc085200647b8ea38a8341a8d8f1f35"
WHEEL_BYTES: Final = 3_632_105
WHEEL_MEMBERS: Final = 1_904
SDIST_SHA256: Final = "25209c5a3ebe192ae79a96511066b6043e738678d1047c0653a4f77cc6be7a49"
SDIST_BYTES: Final = 4_149_161
SDIST_MEMBERS: Final = 4_361


class ReleaseEvidenceError(ValueError):
    """A package or machine-readable receipt is inconsistent."""


def _load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseEvidenceError(f"invalid JSON evidence: {path}") from error
    if not isinstance(value, dict):
        raise ReleaseEvidenceError(f"evidence is not an object: {path}")
    return value


def _artifact(path: Path, expected_sha: str, expected_bytes: int) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ReleaseEvidenceError(f"artifact unavailable: {path}") from error
    if len(payload) != expected_bytes:
        raise ReleaseEvidenceError(f"artifact size mismatch: {path.name}")
    if hashlib.sha256(payload).hexdigest() != expected_sha:
        raise ReleaseEvidenceError(f"artifact digest mismatch: {path.name}")
    return payload


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ReleaseEvidenceError(f"{label} is not an object")
    return value


def verify(
    wheel: Path,
    sdist: Path,
    package_evidence: Path,
    coverage_evidence: Path,
    benchmark_evidence: Path,
    evaluation_evidence: Path,
) -> None:
    _artifact(wheel, WHEEL_SHA256, WHEEL_BYTES)
    _artifact(sdist, SDIST_SHA256, SDIST_BYTES)
    try:
        with zipfile.ZipFile(wheel) as wheel_archive:
            wheel_members = len(wheel_archive.infolist())
        with tarfile.open(sdist) as sdist_archive:
            sdist_members = len(sdist_archive.getmembers())
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise ReleaseEvidenceError("package archive cannot be inspected") from error
    if wheel_members != WHEEL_MEMBERS or sdist_members != SDIST_MEMBERS:
        raise ReleaseEvidenceError("package member count mismatch")
    package = _load(package_evidence)
    wheel_evidence = _object(package.get("wheel"), "wheel evidence")
    sdist_evidence = _object(package.get("sdist"), "sdist evidence")
    if (
        package.get("module_id") != MODULE_ID
        or package.get("reproducible_builds") is not True
        or wheel_evidence.get("sha256") != WHEEL_SHA256
        or sdist_evidence.get("sha256") != SDIST_SHA256
    ):
        raise ReleaseEvidenceError("package evidence does not bind the verified artifacts")
    coverage = _load(coverage_evidence)
    if (
        coverage.get("statements") != 716
        or coverage.get("covered_statements") != 693
        or coverage.get("branches") != 150
        or coverage.get("covered_branches") != 130
        or float(coverage.get("branch_coverage_percent", 0)) < 95.0
    ):
        raise ReleaseEvidenceError("coverage evidence does not meet the locked gate")
    for evidence_path in (benchmark_evidence, evaluation_evidence):
        evidence = _load(evidence_path)
        if evidence.get("module_id") != MODULE_ID or evidence.get("passed") is not True:
            raise ReleaseEvidenceError(f"evaluation evidence failed: {evidence_path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--package-evidence", type=Path, required=True)
    parser.add_argument("--coverage-evidence", type=Path, required=True)
    parser.add_argument("--benchmark-evidence", type=Path, required=True)
    parser.add_argument("--evaluation-evidence", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        verify(**vars(arguments))
    except ReleaseEvidenceError as error:
        parser.error(str(error))
    print("M05-08 release evidence verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

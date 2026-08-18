"""Verify the reproducible package receipt for the M13-M18 depth audit."""

# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import cast
from zipfile import BadZipFile, ZipFile


class EvidenceError(ValueError):
    """Raised when package evidence does not match the supplied artifacts."""


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    return cast("dict[str, object]", value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise EvidenceError(f"{label} must be a non-negative integer")
    return value


def _artifact(report: dict[str, object], label: str) -> tuple[str, int, str]:
    record = _mapping(report.get(label), label)
    return (
        _text(record.get("filename"), f"{label}.filename"),
        _integer(record.get("bytes"), f"{label}.bytes"),
        _text(record.get("sha256"), f"{label}.sha256"),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_artifact(
    artifact_dir: Path,
    label: str,
    expected: tuple[str, int, str],
) -> None:
    filename, expected_bytes, expected_digest = expected
    path = artifact_dir / filename
    if not path.is_file():
        raise EvidenceError(f"{label} artifact is missing: {path}")
    actual_bytes = path.stat().st_size
    if actual_bytes != expected_bytes:
        raise EvidenceError(
            f"{label} byte count mismatch: expected {expected_bytes}, got {actual_bytes}"
        )
    actual_digest = _sha256(path)
    if actual_digest != expected_digest:
        raise EvidenceError(f"{label} sha256 mismatch")
    if label == "wheel":
        try:
            with ZipFile(path) as archive:
                if archive.testzip() is not None:
                    raise EvidenceError("wheel contains a corrupt member")
        except BadZipFile as error:
            raise EvidenceError("wheel is not a valid zip archive") from error


def verify(
    evidence_path: Path,
    first_artifact_dir: Path,
    second_artifact_dir: Path,
) -> None:
    try:
        raw = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"cannot read package evidence: {evidence_path}") from error
    report = _mapping(raw, "package evidence")
    if report.get("status") != "passed":
        raise EvidenceError("package evidence is not marked passed")
    _verify_artifact(first_artifact_dir, "wheel", _artifact(report, "wheel"))
    _verify_artifact(first_artifact_dir, "sdist", _artifact(report, "sdist"))
    wheel = _artifact(report, "wheel")[0]
    sdist = _artifact(report, "sdist")[0]
    for filename in (wheel, sdist):
        first = (first_artifact_dir / filename).read_bytes()
        second_path = second_artifact_dir / filename
        if not second_path.is_file() or second_path.read_bytes() != first:
            raise EvidenceError(f"reproducibility mismatch for {filename}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("first_artifact_dir", type=Path)
    parser.add_argument("second_artifact_dir", type=Path)
    arguments = parser.parse_args()
    try:
        verify(
            arguments.evidence,
            arguments.first_artifact_dir,
            arguments.second_artifact_dir,
        )
    except EvidenceError as error:
        sys.stderr.write(f"M13-M18 release evidence failed: {error}\n")
        return 1
    sys.stdout.write("M13-M18 release evidence passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

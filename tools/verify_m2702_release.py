"""Verify the M27-02 evidence bundle and immutable package artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import cast

MODULE_ID = "GLIO-PROTEOGEN-M27-02"


class ReleaseVerificationError(ValueError):
    """The M27-02 release evidence bundle is inconsistent."""


def _read(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ReleaseVerificationError(  # noqa: TRY003 - include the evidence filename.
            f"evidence must be an object: {path.name}"
        )
    return cast("dict[str, object]", payload)


def _require(condition: object, *, message: str) -> None:
    if not condition:
        raise ReleaseVerificationError(message)


def verify(evidence_dir: Path, package_dir: Path) -> dict[str, object]:
    evaluation = _read(evidence_dir / "evaluation.json")
    benchmark = _read(evidence_dir / "benchmark.json")
    coverage = _read(evidence_dir / "coverage.json")
    package = _read(evidence_dir / "package.json")
    for document in (evaluation, benchmark, coverage, package):
        _require(document.get("module_id") == MODULE_ID, message="evidence module id mismatch")
    _require(evaluation.get("passed") is True, message="evaluator did not pass")
    _require(benchmark.get("passed") is True, message="benchmark did not pass")
    percent = float(cast("float", coverage["percent"]))
    fail_under = float(cast("float", coverage["fail_under"]))
    _require(percent >= fail_under, message="coverage is below fail-under")
    _require(package.get("isolated_import") is True, message="isolated import evidence is missing")
    wheel = cast("dict[str, object]", package["wheel"])
    sdist = cast("dict[str, object]", package["sdist"])
    artifacts = (wheel, sdist)
    for artifact in artifacts:
        path = package_dir / str(artifact["filename"])
        _require(path.is_file(), message=f"package artifact is missing: {path.name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        _require(digest == artifact["sha256"], message=f"package digest mismatch: {path.name}")
        _require(
            path.stat().st_size == artifact["size_bytes"],
            message=f"package size mismatch: {path.name}",
        )
    with zipfile.ZipFile(package_dir / str(wheel["filename"])) as archive:
        _require(
            len(archive.namelist()) == wheel["member_count"],
            message="wheel member count mismatch",
        )
    return {
        "module_id": MODULE_ID,
        "evaluation": True,
        "benchmark": True,
        "coverage": percent,
        "wheel": wheel["sha256"],
        "sdist": sdist["sha256"],
        "verified": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("package_dir", type=Path)
    arguments = parser.parse_args()
    report = verify(arguments.evidence_dir, arguments.package_dir)
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()

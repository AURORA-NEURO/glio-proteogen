"""Verify internally consistent M22-07 release evidence and package identity."""

# ruff: noqa: TRY003, TRY004, FBT001, PLR2004, T201

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile

MODULE_ID = "GLIO-PROTEOGEN-M22-07"
DOSSIER_SHA256 = "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
DOSSIER_SLICE = "GLIO-PROTEOGEN_240_Module_Dossier.md:7860-7900"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(evidence_dir: Path, wheel: Path | None = None, sdist: Path | None = None) -> None:
    evaluation = _load(evidence_dir / "evaluation.json")
    benchmark = _load(evidence_dir / "benchmark.json")
    coverage = _load(evidence_dir / "coverage.json")
    package = _load(evidence_dir / "package.json")
    for report in (evaluation, benchmark, coverage, package):
        _assert(report.get("module_id") == MODULE_ID, "release evidence module identity mismatch")
        _assert(report.get("dossier_sha256") == DOSSIER_SHA256, "authority digest mismatch")
        _assert(report.get("dossier_slice") == DOSSIER_SLICE, "authority slice mismatch")

    checks = evaluation.get("checks")
    _assert(evaluation.get("passed") == 10, "evaluator case inventory changed")
    _assert(evaluation.get("scenario_count") == 10, "evaluator scenario count changed")
    _assert(isinstance(checks, dict) and all(checks.values()), "evaluator did not pass")
    _assert(
        evaluation.get("fixture_digest") == evaluation.get("fixture_request_digest"),
        "fixture request digest is not recorded consistently",
    )
    _assert(benchmark.get("passed") is True, "benchmark budget failed")
    _assert(benchmark.get("iterations") == 10, "benchmark iteration count changed")
    coverage_percent = coverage.get("branch_coverage_percent", 0.0)
    _assert(
        isinstance(coverage_percent, (int, float)) and coverage_percent >= 95.0,
        "coverage below 95 percent",
    )
    _assert(package.get("isolated_import_passed") is True, "isolated import did not pass")
    _assert(package.get("release_verifier_passed") is True, "package verifier was not recorded")
    for candidate, key in ((wheel, "wheel"), (sdist, "sdist")):
        if candidate is None:
            continue
        entry = package.get(key)
        _assert(isinstance(entry, dict), f"{key} package record missing")
        if not isinstance(entry, dict):
            raise TypeError(f"{key} package record is not an object")
        _assert(candidate.is_file(), f"{key} file is missing")
        _assert(entry.get("sha256") == _sha256(candidate), f"{key} hash mismatch")
        _assert(entry.get("size_bytes") == candidate.stat().st_size, f"{key} size mismatch")
        if key == "wheel":
            with ZipFile(candidate) as archive:
                _assert(
                    any(name.endswith("/METADATA") for name in archive.namelist()),
                    "wheel metadata missing",
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, default=Path("release-evidence/m22_07"))
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--sdist", type=Path)
    args = parser.parse_args()
    try:
        verify(args.evidence_dir, args.wheel, args.sdist)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"M22-07 release verification failed: {error}", file=sys.stderr)
        return 1
    print("M22-07 release verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

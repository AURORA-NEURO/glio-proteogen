"""Verify the executable release-evidence bundle for M13-02."""

# Evidence verifier diagnostics intentionally retain stable context in exception messages.
# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from glio_proteogen.kernel.canonical import sha256_digest

MODULE_ID = "GLIO-PROTEOGEN-M13-02"
ROOT = Path(__file__).parents[1]
EVIDENCE = ROOT / "release-evidence" / "m13_02"
FIXTURE = ROOT / "tests" / "fixtures" / "m13_02" / "scenarios.json"
CASE_IDS = (
    "supported_context",
    "limited_context",
    "unresolved_context",
    "conflicted_context",
    "missing_required_dimension",
    "denied_control",
    "tampered_result",
)


class M1302ReleaseVerificationError(ValueError):
    """Raised when release evidence is incomplete or inconsistent."""


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M1302ReleaseVerificationError(f"evidence is not an object: {path.name}")
    return value


def _verify_evaluation() -> None:
    evidence = _json(EVIDENCE / "evaluation.json")
    fixture = _json(FIXTURE)
    if evidence.get("module_id") != MODULE_ID:
        raise M1302ReleaseVerificationError("evaluation module id mismatch")
    if evidence.get("fixture_digest") != sha256_digest(fixture):
        raise M1302ReleaseVerificationError("fixture digest mismatch")
    if evidence.get("declared_cases") != len(CASE_IDS) or evidence.get("executed_cases") != len(
        CASE_IDS
    ):
        raise M1302ReleaseVerificationError("evaluation case count mismatch")
    if evidence.get("passed_cases") != len(CASE_IDS) or evidence.get("all_passed") is not True:
        raise M1302ReleaseVerificationError("evaluation is not green")
    cases = evidence.get("cases")
    if not isinstance(cases, list) or tuple(item.get("case_id") for item in cases) != CASE_IDS:
        raise M1302ReleaseVerificationError("evaluation case IDs are not exact")
    if any(item.get("passed") is not True for item in cases):
        raise M1302ReleaseVerificationError("evaluation contains a failed case")


def _verify_benchmark() -> None:
    evidence = _json(EVIDENCE / "benchmark.json")
    if evidence.get("module_id") != MODULE_ID:
        raise M1302ReleaseVerificationError("benchmark module id mismatch")
    if evidence.get("iterations", 0) < 1:
        raise M1302ReleaseVerificationError("benchmark has no iterations")
    if evidence.get("passed") is not True:
        raise M1302ReleaseVerificationError("benchmark is not green")
    if evidence["mean_ns"] > evidence["mean_budget_ns"]:
        raise M1302ReleaseVerificationError("benchmark mean budget exceeded")
    if evidence["p95_ns"] > evidence["p95_budget_ns"]:
        raise M1302ReleaseVerificationError("benchmark p95 budget exceeded")


def _verify_coverage() -> None:
    evidence = _json(EVIDENCE / "coverage.json")
    if evidence.get("module_id") != MODULE_ID or evidence.get("branch_enabled") is not True:
        raise M1302ReleaseVerificationError("coverage scope is invalid")
    if evidence.get("covered_percent", 0) < evidence.get("fail_under_percent", 95):
        raise M1302ReleaseVerificationError("coverage threshold failed")
    if evidence.get("tests", 0) < 1 or evidence.get("statements", 0) < 1:
        raise M1302ReleaseVerificationError("coverage evidence is empty")


def _members(path: Path) -> int:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return len(archive.namelist())
    with tarfile.open(path, "r:gz") as archive:
        return len(archive.getnames())


def _verify_package(dist_dir: Path) -> None:
    evidence = _json(EVIDENCE / "package.json")
    if evidence.get("module_id") != MODULE_ID:
        raise M1302ReleaseVerificationError("package module id mismatch")
    for kind in ("wheel", "sdist"):
        item = evidence.get(kind)
        if not isinstance(item, dict):
            raise M1302ReleaseVerificationError(f"missing {kind} package evidence")
        path = dist_dir / str(item.get("filename"))
        if not path.is_file():
            raise M1302ReleaseVerificationError(f"missing artifact: {path.name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item.get("sha256"):
            raise M1302ReleaseVerificationError(f"{kind} digest mismatch")
        if path.stat().st_size != item.get("bytes") or _members(path) != item.get("members"):
            raise M1302ReleaseVerificationError(f"{kind} member/size mismatch")
    if evidence.get("isolated_import") is not True or evidence.get("passed") is not True:
        raise M1302ReleaseVerificationError("isolated package import is not green")


def verify_release(dist_dir: Path | None = None) -> dict[str, object]:
    """Verify all M13-02 release evidence and return a compact report."""

    _verify_evaluation()
    _verify_benchmark()
    _verify_coverage()
    _verify_package(dist_dir or ROOT / "dist-m13-02")
    return {"module_id": MODULE_ID, "verified": True, "evidence_dir": str(EVIDENCE)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist-m13-02")
    args = parser.parse_args()
    try:
        sys.stdout.write(json.dumps(verify_release(args.dist_dir), sort_keys=True) + "\n")
    except (OSError, M1302ReleaseVerificationError, KeyError) as exc:
        sys.stderr.write(f"M13-02 release verification failed: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

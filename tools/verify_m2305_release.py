"""Verify M23-05 evaluation, benchmark, coverage, and package evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

MODULE_ID = "GLIO-PROTEOGEN-M23-05"
EVIDENCE_ROOT = Path("release-evidence/m23_05")
DOSSIER_SHA256 = "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
DOSSIER_SLICE = "GLIO-PROTEOGEN_240_Module_Dossier.md:8132-8172"


class M2305ReleaseVerificationError(ValueError):
    """Raised when committed M23-05 evidence is incomplete or inconsistent."""


def _load(root: Path, name: str) -> dict[str, Any]:
    path = root / EVIDENCE_ROOT / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise M2305ReleaseVerificationError(f"cannot read {path}") from error  # noqa: TRY003
    if not isinstance(value, dict):
        raise M2305ReleaseVerificationError(f"{path} must contain an object")  # noqa: TRY003
    return value


def _require(condition: bool, message: str) -> None:  # noqa: FBT001
    if not condition:
        raise M2305ReleaseVerificationError(message)


def _verify_evaluation(root: Path) -> None:
    evidence = _load(root, "evaluation.json")
    _require(evidence.get("module_id") == MODULE_ID, "evaluation module mismatch")
    _require(evidence.get("dossier_sha256") == DOSSIER_SHA256, "evaluation authority mismatch")
    _require(evidence.get("dossier_slice") == DOSSIER_SLICE, "evaluation slice mismatch")
    _require(evidence.get("passed") is True, "evaluation did not pass")
    checks = evidence.get("checks")
    _require(isinstance(checks, dict), "evaluation checks missing")
    checks_map = cast("dict[str, Any]", checks)
    _require(
        evidence.get("scenario_count") == len(checks_map), "evaluation scenario count mismatch"
    )
    _require(all(value is True for value in checks_map.values()), "evaluation checks failed")


def _verify_benchmark(root: Path) -> None:
    evidence = _load(root, "benchmark.json")
    _require(evidence.get("module_id") == MODULE_ID, "benchmark module mismatch")
    _require(evidence.get("passed") is True, "benchmark did not pass")
    mean = evidence.get("mean_ns")
    p95 = evidence.get("p95_ns")
    _require(
        isinstance(mean, (int, float))
        and isinstance(p95, (int, float))
        and mean <= evidence.get("budget_mean_ns", 0)
        and p95 <= evidence.get("budget_p95_ns", 0),
        "benchmark exceeds budget",
    )


def _verify_coverage(root: Path) -> None:
    evidence = _load(root, "coverage.json")
    _require(evidence.get("module_id") == MODULE_ID, "coverage module mismatch")
    _require(evidence.get("branch_enabled") is True, "branch coverage disabled")
    _require(evidence.get("passed") is True, "coverage did not pass")
    _require(
        evidence.get("covered_statements") == evidence.get("statements")
        and evidence.get("covered_branches") == evidence.get("branches")
        and float(evidence.get("coverage_percent", 0.0)) >= float(evidence.get("fail_under", 95.0)),
        "coverage gate failed",
    )


def _verify_package(root: Path) -> None:
    evidence = _load(root, "package.json")
    _require(evidence.get("module_id") == MODULE_ID, "package module mismatch")
    _require(
        evidence.get("passed") is True and evidence.get("isolated_import") is True,
        "package evidence failed",
    )
    for key in ("wheel", "sdist"):
        item = evidence.get(key)
        _require(isinstance(item, dict), f"missing {key} evidence")
        item_map = cast("dict[str, Any]", item)
        filename = item_map.get("filename")
        path = root / "dist" / str(filename)
        _require(path.exists(), f"missing built {key}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        _require(digest == item_map.get("sha256"), f"{key} hash mismatch")
        _require(path.stat().st_size == item_map.get("size_bytes"), f"{key} size mismatch")


def verify(root: Path | None = None) -> None:
    """Verify M23-05 evidence relative to *root* (the current directory by default)."""

    base = root or Path.cwd()
    _verify_evaluation(base)
    _verify_benchmark(base)
    _verify_coverage(base)
    _verify_package(base)


if __name__ == "__main__":
    verify()
    print("M23-05 release evidence verified")  # noqa: T201

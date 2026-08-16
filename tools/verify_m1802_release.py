"""Verify the reviewable M18-02 release-evidence bundle."""

# Evidence verifier output is intentionally human-readable.
# ruff: noqa: C901, PLR0912, T201, TRY003, TRY004

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence" / "m18_02"


def _load(name: str) -> dict[str, Any]:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain an object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify() -> dict[str, object]:
    evaluation = _load("evaluation.json")
    benchmark = _load("benchmark.json")
    coverage = _load("coverage.json")
    package = _load("package.json")
    module_id = "GLIO-PROTEOGEN-M18-02"
    if evaluation.get("module_id") != module_id:
        raise ValueError("evaluation module mismatch")
    if (
        evaluation.get("authority_sha256")
        != "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    ):
        raise ValueError("authority digest mismatch")
    if evaluation.get("authority_lines") != "6200-6240":
        raise ValueError("authority slice mismatch")
    if not evaluation.get("passed") or evaluation.get("declared_cases") != evaluation.get(
        "executed_cases"
    ):
        raise ValueError("evaluation is not closed")
    if not benchmark.get("passed"):
        raise ValueError("benchmark did not pass")
    if int(benchmark["mean_ns"]) > int(benchmark["mean_budget_ns"]):
        raise ValueError("benchmark mean exceeds budget")
    if int(benchmark["p95_ns"]) > int(benchmark["p95_budget_ns"]):
        raise ValueError("benchmark p95 exceeds budget")
    if int(coverage["branch_percent"]) < int(coverage["fail_under"]):
        raise ValueError("coverage is below fail-under")
    files = package.get("artifacts")
    if not isinstance(files, list) or not files:
        raise ValueError("package artifacts are missing")
    checked: list[dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("package artifact entry is not an object")
        relative = item.get("path")
        expected = item.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("package artifact entry is incomplete")
        artifact = ROOT / relative
        if not artifact.is_file() or _sha256(artifact) != expected:
            raise ValueError(f"package artifact mismatch: {relative}")
        checked.append({"path": relative, "sha256": expected})
    return {
        "module_id": module_id,
        "evaluation_cases": evaluation["executed_cases"],
        "branch_percent": coverage["branch_percent"],
        "artifacts": checked,
        "passed": True,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))

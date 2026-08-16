"""Verify the local M18-05 release-evidence bundle."""

# The verifier intentionally reports precise evidence failures at the release boundary.
# ruff: noqa: C901, PLR2004, RUF001, TRY003, TRY004

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence" / "m18_05"
EXPECTED_AUTHORITY_SHA = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


def _read(name: str) -> dict[str, object]:
    with (EVIDENCE / name).open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain an object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify() -> dict[str, object]:
    manifest = (ROOT / "docs" / "modules" / "M18-05.manifest.md").read_text(encoding="utf-8")
    if EXPECTED_AUTHORITY_SHA not in manifest or "6332–6372" not in manifest:
        raise ValueError("authority SHA or exact M18-05 slice is missing")

    evaluation = _read("evaluation.json")
    if (
        evaluation.get("module_id") != "GLIO-PROTEOGEN-M18-05"
        or evaluation.get("declared_cases") != evaluation.get("executed_cases")
        or evaluation.get("passed_cases") != evaluation.get("executed_cases")
        or evaluation.get("passed") is not True
    ):
        raise ValueError("evaluator evidence is not fully passing")

    benchmark = _read("benchmark.json")
    mean_ns = benchmark.get("mean_ns")
    p95_ns = benchmark.get("p95_ns")
    if (
        benchmark.get("module_id") != "GLIO-PROTEOGEN-M18-05"
        or benchmark.get("passed") is not True
        or not isinstance(mean_ns, int)
        or not isinstance(p95_ns, int)
        or mean_ns > MEAN_BUDGET_NS
        or p95_ns > P95_BUDGET_NS
    ):
        raise ValueError("benchmark evidence is not within budget")

    coverage = _read("coverage.json")
    totals = coverage.get("totals")
    if not isinstance(totals, dict):
        raise ValueError("coverage totals are missing")
    branch_percent = totals.get("percent_branches_covered")
    if not isinstance(branch_percent, (int, float)) or branch_percent < 95:
        raise ValueError("scoped branch coverage is below 95 percent")

    package = _read("package.json")
    artifacts = package.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("package evidence has no artifacts")
    checked: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("package artifact record is not an object")
        relative = item.get("path")
        expected_hash = item.get("sha256")
        expected_size = item.get("size_bytes")
        if (
            not isinstance(relative, str)
            or not isinstance(expected_hash, str)
            or not isinstance(expected_size, int)
        ):
            raise ValueError("package artifact record is incomplete")
        path = ROOT / relative
        if (
            not path.is_file()
            or _sha256(path) != expected_hash
            or path.stat().st_size != expected_size
        ):
            raise ValueError(f"package artifact mismatch: {relative}")
        checked.append(relative)
    if package.get("isolated_import") is not True:
        raise ValueError("isolated import evidence is missing")
    return {
        "module_id": "GLIO-PROTEOGEN-M18-05",
        "authority_sha256": EXPECTED_AUTHORITY_SHA,
        "authority_lines": "6332-6372",
        "evaluator": "pass",
        "benchmark": "pass",
        "branch_coverage_percent": branch_percent,
        "artifacts": checked,
        "isolated_import": True,
        "passed": True,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))  # noqa: T201

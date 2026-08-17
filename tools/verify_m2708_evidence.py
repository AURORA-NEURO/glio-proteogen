"""Verify M27-08 local evidence is internally consistent."""

# This tool emits a machine-readable one-line report and checks exact workload identity.
# ruff: noqa: T201, PLR2004
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "m27_08"


def main() -> int:
    evaluation = json.loads((EVIDENCE / "evaluation.json").read_text(encoding="utf-8"))
    benchmark = json.loads((EVIDENCE / "benchmark.json").read_text(encoding="utf-8"))
    coverage = json.loads((EVIDENCE / "coverage.json").read_text(encoding="utf-8"))
    package = json.loads((EVIDENCE / "package.json").read_text(encoding="utf-8"))
    checks = (
        evaluation["passed"] and evaluation["checks_passed"] == evaluation["checks_declared"],
        benchmark["passed"] and benchmark["deterministic"] and benchmark["iterations"] == 10,
        coverage["passed"] and coverage["coverage_percent"] >= coverage["fail_under"],
        package["byte_identical_builds"]
        and package["isolated_import"]
        and package["release_verifier"] == "passed",
    )
    result = {"module_id": "GLIO-PROTEOGEN-M27-08", "checks": len(checks), "passed": all(checks)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

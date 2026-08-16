"""Verify the M22-08 release-evidence manifest and package records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODULE = "GLIO-PROTEOGEN-M22-08"
AUTHORITY = "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
SLICE = "GLIO-PROTEOGEN_240_Module_Dossier.md:7904-7944"


def verify(root: Path) -> dict[str, object]:
    evidence = root / "release-evidence" / "m22_08"
    evaluation = json.loads((evidence / "evaluation.json").read_text(encoding="utf-8"))
    benchmark = json.loads((evidence / "benchmark.json").read_text(encoding="utf-8"))
    checks: dict[str, bool] = {
        "module": evaluation.get("module_id") == MODULE == benchmark.get("module_id"),
        "authority": evaluation.get("dossier_sha256") == AUTHORITY
        and evaluation.get("dossier_slice") == SLICE,
        "evaluation": evaluation.get("passed") is True
        and evaluation.get("passed_cases") == evaluation.get("declared_cases")
        and evaluation.get("passed_cases") == len(evaluation.get("case_ids", [])),
        "benchmark": benchmark.get("passed") is True
        and benchmark.get("mean_ns", 0) <= benchmark.get("mean_budget_ns", -1)
        and benchmark.get("p95_ns", 0) <= benchmark.get("p95_budget_ns", -1)
        and len(benchmark.get("samples_ns", [])) == benchmark.get("iterations"),
    }
    coverage_path = evidence / "coverage.json"
    if coverage_path.exists():
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        checks["coverage"] = coverage.get("branch_enabled") is True and coverage.get(
            "coverage_percent", 0
        ) >= coverage.get("fail_under_percent", 101)
    package_path = evidence / "package.json"
    if package_path.exists():
        package = json.loads(package_path.read_text(encoding="utf-8"))
        checks["package"] = package.get("passed") is True
    return {"module_id": MODULE, "checks": checks, "passed": all(checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    report = verify(parser.parse_args().root)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

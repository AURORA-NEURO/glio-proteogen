"""Verify committed M09 integrated hardening release evidence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).parent
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _load(name: str) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads((ROOT / name).read_text(encoding="utf-8")))


def _check_coverage(coverage: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not coverage["passed"] or coverage["percentCovered"] < coverage["failUnder"]:
        failures.append("coverage")
    statements = coverage["statements"]
    branches = coverage["branches"]
    if statements["covered"] + statements["missing"] != statements["total"]:
        failures.append("statement totals")
    if branches["covered"] + branches["missing"] != branches["total"]:
        failures.append("branch totals")
    return failures


def _check_package(package: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for artifact_name in ("wheel", "sdist"):
        artifact = package[artifact_name]
        if not isinstance(artifact["bytes"], int) or artifact["bytes"] <= 0:
            failures.append(f"{artifact_name} bytes")
        if not _DIGEST.fullmatch(f"sha256:{artifact['sha256']}"):
            failures.append(f"{artifact_name} digest")
        if artifact["generatedMembers"] != 0:
            failures.append(f"{artifact_name} generated members")
    if package["artifactAudit"]["unsafePaths"] != 0 or not package["isolatedImport"]:
        failures.append("package audit")
    return failures


def _check_evaluation(evaluation: dict[str, Any]) -> list[str]:
    if evaluation["focusedTests"]["failed"] != 0 or not all(
        item["passed"] and item["replay"] and item["tamperRejected"]
        for item in evaluation["modules"]
    ):
        return ["evaluation"]
    return []


def _check_benchmark(benchmark: dict[str, Any]) -> list[str]:
    if not all(
        item["passed"]
        and item["meanNs"] <= item["meanBudgetNs"]
        and item["p95Ns"] <= item["p95BudgetNs"]
        for item in benchmark["modules"]
    ):
        return ["benchmark"]
    return []


def main() -> int:
    failures = _check_coverage(_load("coverage.json"))
    failures.extend(_check_package(_load("package.json")))
    failures.extend(_check_evaluation(_load("evaluation.json")))
    failures.extend(_check_benchmark(_load("benchmark.json")))
    if failures:
        raise SystemExit("M09 release evidence failed: " + ", ".join(failures))
    sys.stdout.write("M09 integrated hardening release evidence verified\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

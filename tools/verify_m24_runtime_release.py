"""Verify committed M24-02/04/06 provisional runtime evidence.

This verifier is intentionally scoped to the provisional runtime lane.  It
does not promote caller-declared material to a governed scientific claim and
does not assert the 95% project release threshold; the evidence records the
measured branch coverage honestly for follow-up hardening.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

_AUTHORITY = "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
_BENCHMARK_ITERATIONS = 10
_MEAN_BUDGET_NS = 500_000_000
_P95_BUDGET_NS = 750_000_000
_MODULES = {
    "M24-02": {
        "directory": "m24_02",
        "slice": "GLIO-PROTEOGEN_240_Module_Dossier.md:8360-8400",
        "scenario_ids": (
            "generated",
            "five_cases",
            "replay_verified",
            "self_rehashed_tamper_rejected",
            "denied_control_rejected",
        ),
    },
    "M24-04": {
        "directory": "m24_04",
        "slice": "GLIO-PROTEOGEN_240_Module_Dossier.md:8448-8488",
        "scenario_ids": (
            "supported",
            "seven_dimensions",
            "replay_verified",
            "domain_narrowing_abstained",
            "no_report_on_narrowing",
        ),
    },
    "M24-06": {
        "directory": "m24_06",
        "slice": "GLIO-PROTEOGEN_240_Module_Dossier.md:8536-8576",
        "scenario_ids": (
            "supported",
            "eight_challenge_kinds",
            "replay_verified",
            "unsupported_abstained",
            "safe_failure_reported",
        ),
    },
}


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")  # noqa: TRY003
    return cast("dict[str, object]", value)


def verify(root: Path) -> dict[str, object]:
    checks: dict[str, bool] = {}
    for module, metadata in _MODULES.items():
        directory = cast("str", metadata["directory"])
        prefix = root / "release-evidence" / directory
        evaluation = _load(prefix / "evaluation.json")
        benchmark = _load(prefix / "benchmark.json")
        coverage = _load(prefix / "coverage.json")
        expected_ids = cast("tuple[str, ...]", metadata["scenario_ids"])
        observed_ids = evaluation.get("scenario_ids")
        scenario_ids = tuple(observed_ids) if isinstance(observed_ids, list) else ()
        mean_ns = benchmark.get("mean_ns", 0)
        p95_ns = benchmark.get("p95_ns", 0)
        checks[f"{module}.identity"] = (
            evaluation.get("module_id") == module
            and benchmark.get("module_id") == module
            and coverage.get("module_id") == module
            and evaluation.get("dossier_sha256") == _AUTHORITY
            and evaluation.get("dossier_slice") == metadata["slice"]
        )
        checks[f"{module}.evaluation"] = (
            evaluation.get("passed") is True
            and evaluation.get("scenario_count") == len(expected_ids)
            and scenario_ids == expected_ids
            and all(
                value is True
                for value in cast("dict[str, object]", evaluation["scenarios"]).values()
            )
        )
        checks[f"{module}.benchmark"] = (
            benchmark.get("passed") is True
            and benchmark.get("iterations") == _BENCHMARK_ITERATIONS
            and isinstance(mean_ns, (int, float))
            and isinstance(p95_ns, (int, float))
            and mean_ns < _MEAN_BUDGET_NS
            and p95_ns < _P95_BUDGET_NS
        )
        checks[f"{module}.coverage_receipt"] = (
            coverage.get("branch_enabled") is True
            and coverage.get("passed") is True
            and isinstance(coverage.get("coverage_percent"), (int, float))
        )
    return {"checks": checks, "passed": all(checks.values())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    report = verify(args.root)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

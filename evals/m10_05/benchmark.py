"""Benchmark wrapper for the M10-05 public service boundary."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m10_05.run import build_request
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_05_mechanism_constraint_integrator import (  # noqa: E501
    M1005Service,
)

MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def run_benchmark(*, iterations: int = 10) -> dict[str, object]:
    service = M1005Service()
    request = build_request(soft_expression="always_false")
    service.execute(request)
    samples: list[int] = []
    first_digest = ""
    deterministic = True
    for index in range(iterations):
        start = time.perf_counter_ns()
        result = service.execute(request)
        samples.append(time.perf_counter_ns() - start)
        digest = result.result_digest
        if index == 0:
            first_digest = digest
        deterministic = deterministic and digest == first_digest
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, (len(ordered) * 95 + 99) // 100 - 1))]
    return {
        "module_id": "GLIO-PROTEOGEN-M10-05",
        "iterations": iterations,
        "mean_ns": int(mean(samples)),
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "deterministic": deterministic,
        "result_digest": first_digest,
        "passed": deterministic and mean(samples) <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


def main() -> int:
    report = run_benchmark()
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_benchmark"]

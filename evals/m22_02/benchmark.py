"""Locked microbenchmark wrapper for provisional M22-02."""

from __future__ import annotations

import json
import sys
from statistics import mean, median
from time import perf_counter_ns

from evals.m22_02.run import build_request
from glio_proteogen.modules.c21_reference_material.m22_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2202Service,
)

MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000
ITERATIONS = 10


def run_benchmark(iterations: int = ITERATIONS) -> dict[str, object]:
    service = M2202Service()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        service.generate(request)
        samples.append(perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
    mean_ns = round(mean(samples))
    median_ns = round(median(samples))
    result = {
        "module_id": "GLIO-PROTEOGEN-M22-02",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": mean_ns,
        "median_ns": median_ns,
        "p95_ns": p95,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
    }
    result["passed"] = mean_ns <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS
    return result


def main() -> int:
    result = run_benchmark()
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Locked microbenchmark wrapper for provisional M24-02."""

from __future__ import annotations

import json
from statistics import mean, median
from time import perf_counter_ns
from typing import Any

from glio_proteogen.modules.c21_reference_material import (
    m24_02_synthetic_truth_simulation_generator as m2402,
)

from .fixture import build_request

MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000
ITERATIONS = 10


def run_benchmark(iterations: int = ITERATIONS) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    service = m2402.M2402Service()
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
    return {
        "module_id": "GLIO-PROTEOGEN-M24-02",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": mean_ns,
        "median_ns": median_ns,
        "p95_ns": p95,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean_ns <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


def main() -> int:
    result = run_benchmark()
    print(json.dumps(result, sort_keys=True))  # noqa: T201
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Small deterministic benchmark wrapper for M13-02."""

from __future__ import annotations

import statistics
import time

from evals.m13_02.run import _request
from glio_proteogen.modules.c11_protein_native_subtype.m13_02_context_subtype_stratifier import (
    compute_proteotype_context,
)

MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003 - public helper guard.
    request = _request("supported_context")
    samples: list[int] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        compute_proteotype_context(request)
        samples.append(time.perf_counter_ns() - start)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, (95 * len(ordered) + 99) // 100 - 1))]
    mean = int(statistics.fmean(samples))
    median = int(statistics.median(samples))
    return {
        "iterations": iterations,
        "mean_ns": mean,
        "median_ns": median,
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


if __name__ == "__main__":
    import sys

    sys.stdout.write(f"{run_benchmark()}\n")

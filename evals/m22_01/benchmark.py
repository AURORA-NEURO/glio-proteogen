"""Locked local benchmark wrapper for M22-01 reference curation."""

from __future__ import annotations

import json
from statistics import median
from time import perf_counter_ns
from typing import Any

from glio_proteogen.modules.c21_reference_material.m22_01_reference_truth_benchmark_curator import (
    M2201ReferenceTruthBenchmarkCurator,
)

from .fixture import build_request

MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000


def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    request = build_request()
    engine = M2201ReferenceTruthBenchmarkCurator()
    samples: list[int] = []
    for _ in range(iterations):
        start = perf_counter_ns()
        engine.curate(request)
        samples.append(perf_counter_ns() - start)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    mean_ns = sum(samples) / len(samples)
    p95_ns = ordered[p95_index]
    return {
        "module": "M22-01",
        "iterations": iterations,
        "mean_ns": mean_ns,
        "median_ns": median(samples),
        "p95_ns": p95_ns,
        "budget_mean_ns": MEAN_BUDGET_NS,
        "budget_p95_ns": P95_BUDGET_NS,
        "passed": mean_ns <= MEAN_BUDGET_NS and p95_ns <= P95_BUDGET_NS,
    }


def main() -> None:
    print(json.dumps(run_benchmark(), sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()

"""Locked M23-01 curator benchmark wrapper."""

# ruff: noqa: T201

from __future__ import annotations

import json
import statistics
import time
from typing import Final

from tests.contract.test_m23_01_deep import _request

from glio_proteogen.modules.c21_reference_material.m23_01_reference_truth_benchmark_curator import (
    M2301ReferenceTruthBenchmarkCurator,
)

ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 500_000_000
P95_BUDGET_NS: Final = 750_000_000


def run_benchmark(iterations: int = ITERATIONS) -> dict[str, object]:
    engine = M2301ReferenceTruthBenchmarkCurator()
    request = _request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        engine.curate(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    mean = int(statistics.fmean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M23-01",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": mean,
        "median_ns": int(statistics.median(samples)),
        "p95_ns": p95,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), sort_keys=True))

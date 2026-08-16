"""Locked M22-06 robustness challenge benchmark wrapper."""

# ruff: noqa: T201

from __future__ import annotations

import json
import statistics
import time
from typing import Final

from glio_proteogen.modules.c21_reference_material.m22_06_robustness_shift_ood_challenge import (
    M2206Engine,
)

from .run import build_scenario_request

ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 500_000_000
P95_BUDGET_NS: Final = 750_000_000


def run_benchmark(iterations: int = ITERATIONS) -> dict[str, object]:
    engine = M2206Engine()
    request = build_scenario_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        engine.evaluate(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    mean = int(statistics.fmean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M22-06",
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

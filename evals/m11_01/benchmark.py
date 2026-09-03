"""Small deterministic M11-01 public benchmark."""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m11_01.run import build_scenario_request
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_01_biological_hypothesis_registry as m1101_runtime,
)

BENCHMARK_ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def run_benchmark(iterations: int = BENCHMARK_ITERATIONS) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    request = build_scenario_request("supported_registry")
    engine = m1101_runtime.M1101HypothesisEngine()
    warm = engine.register(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = engine.register(request)
        samples.append(time.perf_counter_ns() - started)
        if result.model_dump(mode="json") != warm.model_dump(mode="json"):
            raise AssertionError
    ordered = sorted(samples)
    average = int(statistics.mean(samples))
    p95 = ordered[max(0, (iterations * 95 + 99) // 100 - 1)]
    return {
        "module_id": "GLIO-PROTEOGEN-M11-01",
        "iterations": iterations,
        "mean_ns": average,
        "median_ns": int(statistics.median(samples)),
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": average <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


__all__ = ["BENCHMARK_ITERATIONS", "MEAN_BUDGET_NS", "P95_BUDGET_NS", "run_benchmark"]

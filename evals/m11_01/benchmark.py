"""Small deterministic M11-01 public benchmark."""

from __future__ import annotations

import statistics
import time
from typing import Final

from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_01_biological_hypothesis_registry as m1101_runtime,
)

from .run import build_scenario_request

BENCHMARK_ITERATIONS: Final = 10


def run_benchmark(iterations: int = BENCHMARK_ITERATIONS) -> dict[str, object]:
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
    return {
        "module_id": "GLIO-PROTEOGEN-M11-01",
        "iterations": iterations,
        "mean_ns": int(statistics.mean(samples)),
        "median_ns": int(statistics.median(samples)),
        "p95_ns": ordered[max(0, int(iterations * 0.95) - 1)],
        "max_ns": max(samples),
    }


__all__ = ["BENCHMARK_ITERATIONS", "run_benchmark"]

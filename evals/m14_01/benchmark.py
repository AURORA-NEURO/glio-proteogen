"""Deterministic M14-01 benchmark wrapper."""

from __future__ import annotations

from statistics import mean, median
from time import perf_counter_ns
from typing import Final

from glio_proteogen.modules.c14_microenvironment_protein_deconvolution.m14_01_biological_hypothesis_registry.engine import (  # noqa: E501
    M1401HypothesisEngine,
)

from .run import build_scenario_request

MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    engine = M1401HypothesisEngine()
    request = build_scenario_request("supported_registry")
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = engine.register(request)
        elapsed = perf_counter_ns() - started
        if result.registry is None:
            raise AssertionError("supported benchmark unexpectedly abstained")  # noqa: TRY003
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, (95 * len(ordered) + 99) // 100 - 1))]
    return {
        "module_id": "GLIO-PROTEOGEN-M14-01",
        "iterations": iterations,
        "mean_ns": int(mean(samples)),
        "median_ns": int(median(samples)),
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": int(mean(samples)) <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


__all__ = ["MEAN_BUDGET_NS", "P95_BUDGET_NS", "run_benchmark"]

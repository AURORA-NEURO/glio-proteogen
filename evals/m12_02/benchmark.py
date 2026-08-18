"""Deterministic M12-02 benchmark wrapper."""

from __future__ import annotations

import sys
from pathlib import Path
from statistics import mean, median
from time import perf_counter_ns
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m12_02.run import build_scenario_request
from glio_proteogen.modules.c12_driver_to_protein_consequence import (
    m12_02_context_subtype_stratifier as m1202_runtime,
)

MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError
    request = build_scenario_request("supported_full")
    engine = m1202_runtime.M1202ContextEngine()
    durations: list[int] = []
    for _ in range(iterations):
        start = perf_counter_ns()
        result = engine.stratify(request)
        engine.verify(result)
        durations.append(perf_counter_ns() - start)
    ordered = sorted(durations)
    p95 = ordered[min(len(ordered) - 1, max(0, (95 * len(ordered) + 99) // 100 - 1))]
    return {
        "iterations": iterations,
        "mean_ns": int(mean(durations)),
        "median_ns": int(median(durations)),
        "p95_ns": p95,
        "max_ns": max(durations),
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "within_budget": mean(durations) <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


__all__ = ["MEAN_BUDGET_NS", "P95_BUDGET_NS", "run_benchmark"]

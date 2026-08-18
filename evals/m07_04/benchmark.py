"""Deterministic benchmark wrapper for provisional M07-04."""

from __future__ import annotations

import sys
from pathlib import Path
from statistics import mean, median
from time import perf_counter_ns

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m07_04.run import request
from glio_proteogen.modules.c07_copy_number_dosage.m07_04_probabilistic_advanced_estimator import (
    M0704Service,
)

_MAX_ITERATIONS = 10_000
_MEAN_BUDGET_NS = 2_000_000_000
_P95_BUDGET_NS = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    """Benchmark complete strict request execution within provisional budgets."""

    if iterations < 1 or iterations > _MAX_ITERATIONS:
        raise ValueError("iterations must be between 1 and 10000")  # noqa: TRY003
    service = M0704Service()
    candidate = request()
    for _ in range(2):
        service.execute(candidate)
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        service.execute(candidate)
        samples.append(perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (len(ordered) * 95 + 99) // 100 - 1)]
    mean_ns = int(mean(samples))
    median_ns = int(median(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M07-04",
        "contract_version": "0.1.0-provisional",
        "iterations": iterations,
        "mean_ns": mean_ns,
        "median_ns": median_ns,
        "p95_ns": p95,
        "mean_budget_ns": _MEAN_BUDGET_NS,
        "p95_budget_ns": _P95_BUDGET_NS,
        "passed": mean_ns <= _MEAN_BUDGET_NS and p95 <= _P95_BUDGET_NS,
    }


__all__ = ["run_benchmark"]

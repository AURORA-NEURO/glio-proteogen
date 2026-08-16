"""Locked M25-05 metadata-only benchmark wrapper."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from evals.m25_05.fixture import build_request
from glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator.engine import (
    M2505SubgroupEquityEngine,
)


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    iterations: int
    samples_ns: tuple[int, ...]
    mean_ns: float
    median_ns: float
    p95_ns: int
    budget_mean_ns: int
    budget_p95_ns: int

    @property
    def passed(self) -> bool:
        return self.mean_ns <= self.budget_mean_ns and self.p95_ns <= self.budget_p95_ns


def run_benchmark(
    *,
    iterations: int = 10,
    budget_mean_ns: int = 500_000_000,
    budget_p95_ns: int = 750_000_000,
) -> BenchmarkSummary:
    """Measure repeated deterministic evaluation without warm-up hiding failures."""

    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    engine = M2505SubgroupEquityEngine()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        engine.generate(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    return BenchmarkSummary(
        iterations=iterations,
        samples_ns=tuple(samples),
        mean_ns=statistics.fmean(samples),
        median_ns=statistics.median(samples),
        p95_ns=ordered[p95_index],
        budget_mean_ns=budget_mean_ns,
        budget_p95_ns=budget_p95_ns,
    )


__all__ = ["BenchmarkSummary", "run_benchmark"]

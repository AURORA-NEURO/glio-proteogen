"""Locked M25-03 microbenchmark wrapper."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Final

from glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation import (
    M2503Service,
)

from .fixture import build_request

BENCHMARK_VERSION: Final = "m25-03-benchmark-v1"
MEAN_BUDGET_NS: Final = 500_000_000
P95_BUDGET_NS: Final = 750_000_000


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Reproducible timing summary for the locked fixture."""

    iterations: int
    samples_ns: tuple[int, ...]
    mean_ns: int
    median_ns: int
    p95_ns: int
    mean_budget_ns: int = MEAN_BUDGET_NS
    p95_budget_ns: int = P95_BUDGET_NS

    @property
    def passed(self) -> bool:
        return self.mean_ns <= self.mean_budget_ns and self.p95_ns <= self.p95_budget_ns


def run_benchmark(iterations: int = 10) -> BenchmarkReport:
    """Run the locked request through the service exactly ``iterations`` times."""

    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    service = M2503Service()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        service.execute(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, (len(ordered) * 95 + 99) // 100 - 1))
    return BenchmarkReport(
        iterations=iterations,
        samples_ns=tuple(samples),
        mean_ns=int(statistics.fmean(samples)),
        median_ns=int(statistics.median(samples)),
        p95_ns=ordered[p95_index],
    )


__all__ = [
    "BENCHMARK_VERSION",
    "MEAN_BUDGET_NS",
    "P95_BUDGET_NS",
    "BenchmarkReport",
    "run_benchmark",
]

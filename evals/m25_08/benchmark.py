"""Reproducible M25-08 deterministic gate benchmark."""

from __future__ import annotations

import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m25_08.fixture import build_request
from glio_proteogen.modules.c21_reference_material import (
    m25_08_evidence_gate_release_adjudicator as m2508,
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
    *, iterations: int = 10, budget_mean_ns: int = 500_000_000, budget_p95_ns: int = 750_000_000
) -> BenchmarkSummary:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    engine = m2508.M2508Engine()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        engine.evaluate(request)
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

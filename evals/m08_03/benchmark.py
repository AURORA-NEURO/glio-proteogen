"""M08-03 baseline benchmark wrapper."""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m08_03.fixtures import request
from glio_proteogen.modules.c08_transcript_protein.m08_03_mature_baseline_estimator import (
    M0803Service,
)

MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


def measure(iterations: int = 10) -> dict[str, float | int]:
    if iterations < 1:
        raise ValueError("benchmark iterations must be positive")  # noqa: TRY003
    service = M0803Service()
    candidate = request()
    durations: list[int] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        service.execute(candidate)
        durations.append(time.perf_counter_ns() - start)
    ordered = sorted(durations)
    return {
        "iterations": iterations,
        "mean_ns": float(statistics.mean(durations)),
        "median_ns": float(statistics.median(durations)),
        "p95_ns": float(ordered[max(0, int(iterations * 0.95) - 1)]),
    }


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    """Run and normalize the existing M08-03 service workload."""

    report = measure(iterations)
    return {
        "module_id": "GLIO-PROTEOGEN-M08-03",
        **report,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": report["mean_ns"] <= MEAN_BUDGET_NS and report["p95_ns"] <= P95_BUDGET_NS,
    }

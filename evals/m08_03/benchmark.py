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

"""Small deterministic benchmark wrapper for M15-07 release evidence."""

# ruff: noqa: E501, TRY003

from __future__ import annotations

import sys
from pathlib import Path
from statistics import mean
from time import perf_counter_ns

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.modules.c15_longitudinal_recurrence.test_m15_07_engine import _request

from glio_proteogen.contracts.m15_07 import PlausibilityAdjudicationStatus
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_07_plausibility_negative_control_adjudicator import (
    M1507PlausibilityAdjudicator,
)

MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


def measure(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    engine = M1507PlausibilityAdjudicator()
    request = _request()
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = engine.adjudicate(request)
        elapsed = perf_counter_ns() - started
        if result.status is not PlausibilityAdjudicationStatus.ADJUDICATED:
            raise RuntimeError("benchmark request did not adjudicate")
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
    mean_ns = int(mean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M15-07",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": mean_ns,
        "median_ns": ordered[len(ordered) // 2],
        "p95_ns": p95,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean_ns <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }

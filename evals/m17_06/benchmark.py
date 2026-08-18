"""Deterministic benchmark wrapper for M17-06 release evidence."""

# ruff: noqa: TRY003

from __future__ import annotations

import sys
from pathlib import Path
from statistics import mean
from time import perf_counter_ns

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.contract.test_m17_06_deep import _request

from glio_proteogen.contracts.m17_06 import QueueResultStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_06_reviewer_discrepancy_adjudication as m1706,
)

MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


def measure(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    engine = m1706.M1706AdjudicationEngine()
    request = _request()
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = engine.export(request)
        elapsed = perf_counter_ns() - started
        if result.status is not QueueResultStatus.RECORDED:
            raise RuntimeError("benchmark request was not recorded")
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
    mean_ns = int(mean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M17-06",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": mean_ns,
        "median_ns": ordered[len(ordered) // 2],
        "p95_ns": p95,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean_ns <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }

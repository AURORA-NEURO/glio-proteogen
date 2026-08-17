"""Deterministic benchmark wrapper for M17-02 release evidence."""

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

from tests.contract.test_m17_02_deep import _request

from glio_proteogen.contracts.m17_02 import AlignmentResultStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_02_cross_source_alignment_reconciliation as m1702,
)

MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


def measure(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    engine = m1702.M1702AlignmentEngine()
    request = _request()
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = engine.export(request)
        elapsed = perf_counter_ns() - started
        if result.status is not AlignmentResultStatus.RECONCILED:
            raise RuntimeError("benchmark request was not reconciled")
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
    mean_ns = int(mean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M17-02",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": mean_ns,
        "median_ns": ordered[len(ordered) // 2],
        "p95_ns": p95,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean_ns <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }

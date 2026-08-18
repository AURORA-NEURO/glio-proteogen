"""Deterministic benchmark wrapper for M16-07 release evidence."""

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

from tests.modules.c16_kinophos_object_consumer.test_m16_07_engine import _request

from glio_proteogen.contracts.m16_07 import ExportStatus
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_07_downstream_typed_export import (
    M1607ExportEngine,
)

MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


def measure(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    engine = M1607ExportEngine()
    request = _request()
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = engine.export(request)
        elapsed = perf_counter_ns() - started
        if result.status is not ExportStatus.SIGNED:
            raise RuntimeError("benchmark request was not signed")
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
    mean_ns = int(mean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M16-07",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": mean_ns,
        "median_ns": ordered[len(ordered) // 2],
        "p95_ns": p95,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean_ns <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }

"""Locked M26-01 registry benchmark wrapper."""

# ruff: noqa: T201

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.contract.test_m2601_deep import _request

from glio_proteogen.modules.c20_biomarker_panel.m26_01_registry_configuration_service import (
    M2601RegistryEngine,
)

ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 500_000_000
P95_BUDGET_NS: Final = 750_000_000


def run_benchmark(iterations: int = ITERATIONS) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("benchmark iterations must be positive")  # noqa: TRY003
    engine = M2601RegistryEngine()
    request = _request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        engine.register(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    mean = int(statistics.fmean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M26-01",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": mean,
        "median_ns": int(statistics.median(samples)),
        "p95_ns": p95,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), sort_keys=True))

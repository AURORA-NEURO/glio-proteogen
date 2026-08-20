"""Locked microbenchmark wrapper for provisional M25-04."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean, median
from time import perf_counter_ns
from typing import Any

if __package__ in {None, ""}:
    _SOURCE_ROOT = Path(__file__).resolve().parents[2]
    if str(_SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SOURCE_ROOT))

from evals.m25_04.fixture import build_request
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator import (
    M2504Service,
)

MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000
ITERATIONS = 10


def run_benchmark(iterations: int = ITERATIONS) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    service = M2504Service()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        service.execute(request)
        samples.append(perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
    mean_ns = round(mean(samples))
    median_ns = round(median(samples))
    return {
        "iterations": iterations,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "mean_ns": mean_ns,
        "median_ns": median_ns,
        "module_id": "GLIO-PROTEOGEN-M25-04",
        "p95_budget_ns": P95_BUDGET_NS,
        "p95_ns": p95,
        "passed": mean_ns <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
        "samples_ns": samples,
    }


def main() -> int:
    result = run_benchmark()
    print(json.dumps(result, sort_keys=True))  # noqa: T201
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

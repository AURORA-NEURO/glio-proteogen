"""Locked local benchmark wrapper for M23-02 generation."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.modules.c21_reference_material.m23_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2302Service,
)

if __package__ in {None, ""}:
    from evals.m23_02.fixture import build_request
else:
    from .fixture import build_request

ITERATIONS: Final = 10
MEAN_BUDGET_NS: Final = 500_000_000
P95_BUDGET_NS: Final = 750_000_000


def run_benchmark(iterations: int = ITERATIONS) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    service = M2302Service()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        service.execute(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
    mean = int(statistics.fmean(samples))
    return {
        "module": "M23-02",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": mean,
        "median_ns": int(statistics.median(samples)),
        "p95_ns": p95,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


def main() -> None:
    print(json.dumps(run_benchmark(), sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["main", "run_benchmark"]

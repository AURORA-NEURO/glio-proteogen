"""Locked microbenchmark wrapper for M21-01."""

from __future__ import annotations

import json
import statistics
import time
from typing import Any

from glio_proteogen.modules.c21_reference_material.m21_01_reference_truth_benchmark_curator import (
    M2101Service,
)

from .fixture import build_request

_BUDGET_MEAN_NS = 500_000_000
_BUDGET_P95_NS = 750_000_000


def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    """Measure deterministic in-process curation with a fixed fixture."""

    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    service = M2101Service()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        service.execute(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, (len(ordered) * 95 + 99) // 100 - 1)]
    return {
        "module": "M21-01",
        "iterations": iterations,
        "mean_ns": round(statistics.fmean(samples)),
        "median_ns": round(statistics.median(samples)),
        "p95_ns": p95,
        "budget_mean_ns": _BUDGET_MEAN_NS,
        "budget_p95_ns": _BUDGET_P95_NS,
        "passed": statistics.fmean(samples) <= _BUDGET_MEAN_NS and p95 <= _BUDGET_P95_NS,
    }


def main() -> None:
    print(json.dumps(run_benchmark(), sort_keys=True, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["main", "run_benchmark"]

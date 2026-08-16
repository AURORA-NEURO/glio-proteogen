"""Locked microbenchmark wrapper for M25-06."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Any

from glio_proteogen.modules.c21_reference_material.m25_06_robustness_shift_ood_challenge import (
    M2506RobustnessEngine,
)

from .fixture import build_request

_MEAN_BUDGET_NS = 500_000_000
_P95_BUDGET_NS = 750_000_000


def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    engine = M2506RobustnessEngine()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        engine.challenge(request)
        samples.append(time.perf_counter_ns() - start)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return {
        "module": "M25-06",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": round(statistics.mean(samples), 2),
        "median_ns": round(statistics.median(samples), 2),
        "p95_ns": p95,
        "budget_mean_ns": _MEAN_BUDGET_NS,
        "budget_p95_ns": _P95_BUDGET_NS,
        "passed": statistics.mean(samples) < _MEAN_BUDGET_NS and p95 < _P95_BUDGET_NS,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(run_benchmark(args.iterations), sort_keys=True, indent=2))  # noqa: T201


if __name__ == "__main__":
    main()


__all__ = ["run_benchmark"]

"""Locked local microbenchmark for M24-06 deterministic challenge."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from typing import Any

from evals.m24_06.fixture import build_request
from glio_proteogen.modules.c21_reference_material.m24_06_robustness_shift_ood_challenge import (
    M2406Service,
)

MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000


def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    service = M2406Service()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        service.challenge(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
    mean = statistics.fmean(samples)
    return {
        "module": "M24-06",
        "iterations": iterations,
        "mean_ns": mean,
        "median_ns": statistics.median(samples),
        "p95_ns": p95,
        "budget_mean_ns": MEAN_BUDGET_NS,
        "budget_p95_ns": P95_BUDGET_NS,
        "passed": mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()
    report = run_benchmark(args.iterations)
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


__all__ = ["run_benchmark"]

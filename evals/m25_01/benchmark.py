"""Locked microbenchmark wrapper for M25-01 curation."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from typing import Any

from glio_proteogen.modules.c21_reference_material.m25_01_reference_truth_benchmark_curator import (
    M2501ReferenceTruthBenchmarkCurator,
)

from .fixture import build_request

MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000
ITERATIONS = 10


def run_benchmark(iterations: int = ITERATIONS) -> dict[str, Any]:
    request = build_request()
    engine = M2501ReferenceTruthBenchmarkCurator()
    engine.curate(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = engine.curate(request)
        elapsed = time.perf_counter_ns() - started
        if result.package is None:
            raise RuntimeError("benchmark fixture unexpectedly abstained")  # noqa: TRY003
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, (len(ordered) * 95 + 99) // 100 - 1))]
    mean = int(statistics.fmean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M25-01",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": mean,
        "median_ns": int(statistics.median(samples)),
        "p95_ns": p95,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=ITERATIONS)
    args = parser.parse_args()
    report = run_benchmark(args.iterations)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

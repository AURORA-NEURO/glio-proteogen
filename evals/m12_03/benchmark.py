"""Small deterministic M12-03 benchmark wrapper."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Final

from evals.m12_03.run import build_request
from glio_proteogen.modules.c12_driver_protein_consequence import construct_mechanistic_features

MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = construct_mechanistic_features(request)
        elapsed = time.perf_counter_ns() - started
        if result.feature_object is None:
            raise RuntimeError("benchmark fixture unexpectedly abstained")  # noqa: TRY003
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[max(0, min(len(ordered) - 1, (len(ordered) * 95 + 99) // 100 - 1))]
    return {
        "module_id": "GLIO-PROTEOGEN-M12-03",
        "iterations": iterations,
        "mean_ns": round(statistics.fmean(samples)),
        "median_ns": round(statistics.median(samples)),
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": statistics.fmean(samples) <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(run_benchmark(args.iterations), indent=2, sort_keys=True))  # noqa: T201

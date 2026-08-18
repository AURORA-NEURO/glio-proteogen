"""Microbenchmark wrapper for M18-02 deterministic alignment."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m18_02.run import build_scenario_request
from glio_proteogen.modules.c18_spatial_proteomics.m18_02_cross_source_alignment import (
    M1802CrossSourceAlignmentEngine,
)

MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    engine = M1802CrossSourceAlignmentEngine()
    request = build_scenario_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        engine.infer(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
    mean = int(statistics.mean(samples))
    median = int(statistics.median(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M18-02",
        "iterations": iterations,
        "mean_ns": mean,
        "median_ns": median,
        "p95_ns": p95,
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    print(json.dumps(run_benchmark(parser.parse_args().iterations), sort_keys=True))  # noqa: T201

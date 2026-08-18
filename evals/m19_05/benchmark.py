"""Microbenchmark wrapper for deterministic M19-05 presentation."""

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

from evals.m19_05.scenarios import build_request
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_05_workflow_presentation_service import (  # noqa: E501
    M1905Engine,
)

MEAN_BUDGET_NS = 2_000_000_000
P95_BUDGET_NS = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError
    engine = M1905Engine()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        engine.present(request)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
    mean = int(statistics.mean(samples))
    median = int(statistics.median(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M19-05",
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

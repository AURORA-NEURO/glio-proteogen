"""Small deterministic benchmark wrapper for M12-05."""

# CLI evidence runner intentionally prints its machine-readable report.
# ruff: noqa: T201, TRY003

from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Final

from evals.m12_05.run import build_scenario_request
from glio_proteogen.modules.c12_driver_to_protein_consequence.m12_05_longitudinal_evolution import (
    M1205LongitudinalEngine,
)

MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    engine = M1205LongitudinalEngine()
    request = build_scenario_request()
    durations: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        engine.infer(request)
        durations.append(time.perf_counter_ns() - started)
    ordered = sorted(durations)
    p95 = ordered[min(len(ordered) - 1, (len(ordered) * 95 + 99) // 100 - 1)]
    mean = int(statistics.mean(durations))
    return {
        "module_id": "GLIO-PROTEOGEN-M12-05",
        "iterations": iterations,
        "mean_ns": mean,
        "median_ns": int(statistics.median(durations)),
        "p95_ns": p95,
        "max_ns": max(durations),
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    report = run_benchmark(parser.parse_args().iterations)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

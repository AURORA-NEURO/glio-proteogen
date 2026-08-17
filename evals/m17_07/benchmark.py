"""Small deterministic M17-07 public-operation benchmark."""

# CLI output and fixed benchmark values are intentionally explicit.
# ruff: noqa: T201

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean, median
from time import perf_counter_ns

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m17_07.run import build_scenario_request
from glio_proteogen.modules.c17_metabolomic_lipidomic.m17_07_downstream_typed_export import (
    M1707DownstreamTypedExportEngine,
)


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    engine = M1707DownstreamTypedExportEngine()
    request = build_scenario_request()
    engine.infer(request)
    durations: list[int] = []
    for _ in range(iterations):
        start = perf_counter_ns()
        engine.infer(request)
        durations.append(perf_counter_ns() - start)
    ordered = sorted(durations)
    mean_ns = round(mean(durations))
    median_ns = round(median(durations))
    p95_ns = ordered[max(0, int(iterations * 0.95) - 1)]
    mean_budget_ns = 2_000_000_000
    p95_budget_ns = 3_000_000_000
    result = {
        "module_id": "GLIO-PROTEOGEN-M17-07",
        "iterations": iterations,
        "mean_ns": mean_ns,
        "median_ns": median_ns,
        "p95_ns": p95_ns,
        "mean_budget_ns": mean_budget_ns,
        "p95_budget_ns": p95_budget_ns,
    }
    result["passed"] = bool(mean_ns <= mean_budget_ns and p95_ns <= p95_budget_ns)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    print(json.dumps(run_benchmark(parser.parse_args().iterations), sort_keys=True))

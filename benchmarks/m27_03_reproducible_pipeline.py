"""Locked M27-03 orchestration microbenchmark."""


from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.m27_03.fixtures import request

from glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator import (
    M2703Engine,
)

_MEAN_BUDGET_NS = 500_000_000
_P95_BUDGET_NS = 750_000_000


def run(iterations: int = 10) -> dict[str, float | int]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    engine = M2703Engine()
    candidate = request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = engine.execute(candidate)
        samples.append(time.perf_counter_ns() - started)
        if result.execution_record is None:
            raise RuntimeError("benchmark fixture unexpectedly abstained")  # noqa: TRY003
    ordered = sorted(samples)
    mean_ns = float(statistics.mean(samples))
    p95_ns = float(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))])
    return {
        "moduleId": "GLIO-PROTEOGEN-M27-03",
        "iterations": iterations,
        "mean_ns": mean_ns,
        "median_ns": float(statistics.median(samples)),
        "p95_ns": p95_ns,
        "budget_mean_ns": _MEAN_BUDGET_NS,
        "budget_p95_ns": _P95_BUDGET_NS,
        "budgetPassed": mean_ns <= _MEAN_BUDGET_NS and p95_ns <= _P95_BUDGET_NS,
    }


if __name__ == "__main__":
    sys.stdout.write(json.dumps(run(), sort_keys=True) + "\n")

"""Locked M27-03 orchestration microbenchmark."""

from __future__ import annotations

import json
import statistics
import sys
import time

from evals.m27_03.fixtures import request

from glio_proteogen.modules.c27_complex_activity.m27_03_reproducible_pipeline_orchestrator import (
    M2703Engine,
)


def run(iterations: int = 10) -> dict[str, float | int]:
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
    return {
        "iterations": iterations,
        "mean_ns": float(statistics.mean(samples)),
        "median_ns": float(statistics.median(samples)),
        "p95_ns": float(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]),
    }


if __name__ == "__main__":
    sys.stdout.write(json.dumps(run(), sort_keys=True) + "\n")

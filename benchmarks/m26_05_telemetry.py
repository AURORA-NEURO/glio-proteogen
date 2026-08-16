"""Locked microbenchmark wrapper for the M26-05 telemetry service."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from typing import Any

from evals.m26_05.fixture import make_request

from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry import (
    M2605ObservabilityService,
)

_MEAN_BUDGET_NS = 500_000_000
_P95_BUDGET_NS = 750_000_000


def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    service = M2605ObservabilityService()
    request = make_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = service.execute(request)
        elapsed = time.perf_counter_ns() - started
        if result.status.value != "emitted":
            raise RuntimeError("benchmark fixture unexpectedly abstained")  # noqa: TRY003
        samples.append(elapsed)
    ordered = sorted(samples)
    return {
        "moduleId": "GLIO-PROTEOGEN-M26-05",
        "iterations": iterations,
        "samplesNs": samples,
        "meanNs": round(statistics.mean(samples), 2),
        "medianNs": round(statistics.median(samples), 2),
        "p95Ns": ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))],
        "budgetsNs": {"mean": _MEAN_BUDGET_NS, "p95": _P95_BUDGET_NS},
        "budgetPassed": statistics.mean(samples) <= _MEAN_BUDGET_NS
        and ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))] <= _P95_BUDGET_NS,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()
    sys.stdout.write(json.dumps(run_benchmark(args.iterations), sort_keys=True, indent=2) + "\n")


__all__ = ["run_benchmark"]

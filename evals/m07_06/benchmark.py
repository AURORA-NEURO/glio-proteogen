"""Small deterministic benchmark wrapper for M07-06."""

from __future__ import annotations

import statistics
import sys
import time
from typing import Any

from evals.m07_06.run import load_request
from glio_proteogen.modules.c07_copy_number_dosage.m07_06_uncertainty_decomposition import (
    M0706Service,
)

_MEAN_BUDGET_NS = 2_000_000_000
_P95_BUDGET_NS = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    """Measure strict service execution with a frozen request."""

    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    service = M0706Service()
    request = load_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = service.execute(request)
        samples.append(time.perf_counter_ns() - started)
        if result.result_digest != service.execute(request).result_digest:
            raise AssertionError("benchmark execution is not deterministic")  # noqa: TRY003
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return {
        "module_id": "GLIO-PROTEOGEN-M07-06",
        "iterations": iterations,
        "mean_ns": round(statistics.mean(samples)),
        "median_ns": round(statistics.median(samples)),
        "p95_ns": p95,
        "budget_ns": _MEAN_BUDGET_NS,
        "p95_budget_ns": _P95_BUDGET_NS,
        "passed": statistics.mean(samples) < _MEAN_BUDGET_NS and p95 < _P95_BUDGET_NS,
    }


if __name__ == "__main__":
    import json

    sys.stdout.write(json.dumps(run_benchmark(), indent=2, sort_keys=True) + "\n")

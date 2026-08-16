"""Deterministic bounded benchmark wrapper for M08-06."""

from __future__ import annotations

import statistics
import sys
import time
from typing import Any

from evals.m08_06.run import load_request
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_06_uncertainty_decomposition import (  # noqa: E501
    M0806Service,
)

_MEAN_BUDGET_NS = 2_000_000_000
_P95_BUDGET_NS = 3_000_000_000


def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    """Measure strict service execution against a frozen request."""

    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    service = M0806Service()
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
    mean = statistics.mean(samples)
    return {
        "module_id": "GLIO-PROTEOGEN-M08-06",
        "iterations": iterations,
        "mean_ns": round(mean),
        "median_ns": round(statistics.median(samples)),
        "p95_ns": p95,
        "budget_ns": _MEAN_BUDGET_NS,
        "p95_budget_ns": _P95_BUDGET_NS,
        "passed": mean < _MEAN_BUDGET_NS and p95 < _P95_BUDGET_NS,
    }


if __name__ == "__main__":
    import json

    sys.stdout.write(json.dumps(run_benchmark(), indent=2, sort_keys=True) + "\n")

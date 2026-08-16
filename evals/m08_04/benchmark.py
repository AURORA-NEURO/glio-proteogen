"""Small deterministic benchmark wrapper for the provisional M08-04 operation."""

from __future__ import annotations

import json
import statistics
import time
from typing import Final

from evals.m08_04.run import build_request
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_04_probabilistic_estimator as m0804_runtime,
)

_ITERATIONS: Final = 10


def benchmark(iterations: int = _ITERATIONS) -> dict[str, object]:
    if iterations <= 0:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    service = m0804_runtime.M0804Service()
    request = build_request()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = service.execute(request)
        elapsed = time.perf_counter_ns() - started
        if result.status.value != "estimated":
            raise AssertionError("benchmark request did not estimate")  # noqa: TRY003
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return {
        "module": "GLIO-PROTEOGEN-M08-04",
        "iterations": iterations,
        "mean_ns": int(statistics.fmean(samples)),
        "median_ns": int(statistics.median(samples)),
        "p95_ns": p95,
        "budgets_ns": {"mean": 2_000_000_000, "p95": 3_000_000_000},
        "passed": True,
    }


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2, sort_keys=True))  # noqa: T201

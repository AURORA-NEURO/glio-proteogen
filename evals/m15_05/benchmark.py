"""Representative M15-05 bounded temporal replay benchmark."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.runtime.test_m15_05_engine import _request

from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_05_longitudinal_evolution as m1505,
)

_ITERATIONS = 100
_MEAN_BUDGET_NS = 2_000_000_000
_P95_BUDGET_NS = 3_000_000_000


class _BenchmarkError(RuntimeError):
    pass


def run_benchmark(iterations: int = _ITERATIONS) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    request = _request()
    service = m1505.M1505Service()
    service.construct(request)
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = service.construct(request)
        samples.append(time.perf_counter_ns() - started)
        if result.status.value != "modeled":
            raise _BenchmarkError
    ordered = sorted(samples)
    p95 = ordered[max(0, (iterations * 95 + 99) // 100 - 1)]
    average = int(statistics.mean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M15-05",
        "iterations": iterations,
        "mean_seconds": average / 1_000_000_000,
        "best_seconds": min(samples) / 1_000_000_000,
        "mean_ns": average,
        "median_ns": int(statistics.median(samples)),
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": _MEAN_BUDGET_NS,
        "p95_budget_ns": _P95_BUDGET_NS,
        "passed": average <= _MEAN_BUDGET_NS and p95 <= _P95_BUDGET_NS,
        "scope": "public ordered caller-declared metadata replay only",
    }


def main() -> int:
    report = run_benchmark()
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Small deterministic M16-06 queue replay benchmark."""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from time import perf_counter_ns
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.runtime.test_m16_06_queue import _request

from glio_proteogen.modules.c16_kinophos_object_consumer import M1606Engine

BENCHMARK_ITERATIONS: Final = 100
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def run_benchmark(iterations: int = BENCHMARK_ITERATIONS) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    engine = M1606Engine()
    request = _request()
    durations: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        engine.adjudicate(request)
        durations.append(perf_counter_ns() - started)
    ordered = sorted(durations)
    p95 = ordered[max(0, (iterations * 95 + 99) // 100 - 1)]
    average = int(statistics.mean(durations))
    return {
        "module_id": "GLIO-PROTEOGEN-M16-06",
        "iterations": iterations,
        "mean_seconds": average / 1_000_000_000,
        "best_seconds": min(durations) / 1_000_000_000,
        "mean_ns": average,
        "median_ns": int(statistics.median(durations)),
        "p95_ns": p95,
        "max_ns": max(durations),
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": average <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
        "scope": "public typed reviewer queue metadata only",
    }


def main() -> dict[str, object]:
    return run_benchmark()


if __name__ == "__main__":
    sys.stdout.write(json.dumps(main(), sort_keys=True) + "\n")

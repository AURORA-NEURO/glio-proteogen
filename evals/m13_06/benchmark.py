"""Representative M13-06 bounded replay benchmark."""

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

from evals.m13_06.run import _request
from glio_proteogen.modules.c13_proteotype.m13_06_perturbation_sensitivity import (
    simulate_proteotype_perturbation_sensitivity,
)

BENCHMARK_ITERATIONS: Final = 100
MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


def run_benchmark(iterations: int = BENCHMARK_ITERATIONS) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    corpus = json.loads(
        (Path(__file__).parents[2] / "tests" / "fixtures" / "m13_06" / "scenarios.json").read_text()
    )
    case = next(item for item in corpus["cases"] if item["expected"] == "simulated")
    request = _request(case)
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        simulate_proteotype_perturbation_sensitivity(request)
        samples.append(perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[max(0, (iterations * 95 + 99) // 100 - 1)]
    average = int(statistics.mean(samples))
    return {
        "module_id": corpus["module_id"],
        "iterations": iterations,
        "best_seconds": min(samples) / 1_000_000_000,
        "mean_seconds": average / 1_000_000_000,
        "mean_ns": average,
        "median_ns": int(statistics.median(samples)),
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": average <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
        "scope": "public bounded replay operation only",
    }


def main() -> None:
    sys.stdout.write(json.dumps(run_benchmark(), sort_keys=True) + "\n")


if __name__ == "__main__":
    main()

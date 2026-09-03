"""Repeatable M24-07 benchmark wrapper."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean, median
from time import perf_counter_ns

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m24_07.fixture import request
from glio_proteogen.modules.c21_reference_material import (
    m24_07_human_factors_operational_evaluator as m2407,
)

_MAX_ITERATIONS = 1000
_MEAN_BUDGET_NS = 500_000_000
_P95_BUDGET_NS = 750_000_000


class M2407BenchmarkError(ValueError):
    """Raised when a benchmark request is outside locked bounds."""

    def __init__(self) -> None:
        super().__init__("iterations must be between 1 and 1000")


def run(iterations: int = 10) -> dict[str, bool | float | int | str]:
    if iterations < 1 or iterations > _MAX_ITERATIONS:
        raise M2407BenchmarkError
    service = m2407.M2407Service()
    candidate = request()
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        service.evaluate(candidate)
        samples.append(perf_counter_ns() - started)
    ordered = sorted(samples)
    mean_ns = float(mean(samples))
    p95_ns = float(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))])
    return {
        "module_id": "GLIO-PROTEOGEN-M24-07",
        "iterations": iterations,
        "mean_ns": mean_ns,
        "median_ns": float(median(samples)),
        "p95_ns": p95_ns,
        "min_ns": float(ordered[0]),
        "max_ns": float(ordered[-1]),
        "mean_budget_ns": _MEAN_BUDGET_NS,
        "p95_budget_ns": _P95_BUDGET_NS,
        "passed": mean_ns <= _MEAN_BUDGET_NS and p95_ns <= _P95_BUDGET_NS,
    }


def main() -> None:
    sys.stdout.write(json.dumps(run(), sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()

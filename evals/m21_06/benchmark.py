"""Locked local benchmark wrapper for M21-06 robustness evaluation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Any

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m21_06.fixture import supported_request
from glio_proteogen.modules.c21_reference_material.m21_06_robustness_shift_ood_challenge import (
    M2106Engine,
)

MEAN_BUDGET_NS = 500_000_000
P95_BUDGET_NS = 750_000_000


def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    request = supported_request()
    engine = M2106Engine()
    samples: list[int] = []
    for _ in range(iterations):
        start = perf_counter_ns()
        engine.generate(request)
        samples.append(perf_counter_ns() - start)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    mean_ns = sum(samples) / len(samples)
    p95_ns = ordered[p95_index]
    return {
        "module": "M21-06",
        "iterations": iterations,
        "mean_ns": mean_ns,
        "median_ns": median(samples),
        "p95_ns": p95_ns,
        "budget_mean_ns": MEAN_BUDGET_NS,
        "budget_p95_ns": P95_BUDGET_NS,
        "passed": mean_ns <= MEAN_BUDGET_NS and p95_ns <= P95_BUDGET_NS,
    }


def main() -> None:
    print(json.dumps(run_benchmark(), sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()

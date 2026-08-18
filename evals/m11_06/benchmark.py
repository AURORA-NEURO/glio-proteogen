"""Small deterministic benchmark wrapper for M11-06."""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from evals.m11_06.run import build_scenario_request
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_06_perturbation_sensitivity_simulator as m1106_runtime,
)

MEAN_BUDGET_NS: Final = 2_000_000_000
P95_BUDGET_NS: Final = 3_000_000_000


class M1106BenchmarkError(ValueError):
    """Invalid benchmark configuration or fixture result."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"M11-06 benchmark error: {reason}")


class M1106InvalidIterationsError(M1106BenchmarkError):
    """The benchmark iteration count is not positive."""

    def __init__(self) -> None:
        super().__init__("iterations must be positive")


class M1106FixtureResultError(M1106BenchmarkError):
    """The benchmark fixture did not produce a supported simulation."""

    def __init__(self) -> None:
        super().__init__("benchmark fixture did not produce a simulated result")


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    if iterations < 1:
        raise M1106InvalidIterationsError
    request = build_scenario_request()
    engine = m1106_runtime.M1106SensitivityEngine()
    samples: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = engine.register(request)
        elapsed = time.perf_counter_ns() - started
        if result.status.value != "simulated":
            raise M1106FixtureResultError
        samples.append(elapsed)
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    mean = int(statistics.fmean(samples))
    return {
        "module_id": "GLIO-PROTEOGEN-M11-06",
        "iterations": iterations,
        "mean_ns": mean,
        "median_ns": int(statistics.median(samples)),
        "p95_ns": p95,
        "max_ns": max(samples),
        "mean_budget_ns": MEAN_BUDGET_NS,
        "p95_budget_ns": P95_BUDGET_NS,
        "passed": mean <= MEAN_BUDGET_NS and p95 <= P95_BUDGET_NS,
    }


__all__ = [
    "MEAN_BUDGET_NS",
    "P95_BUDGET_NS",
    "M1106BenchmarkError",
    "M1106FixtureResultError",
    "M1106InvalidIterationsError",
    "run_benchmark",
]

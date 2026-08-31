"""Fresh-process adapter for legacy pytest-benchmark workloads.

The historical benchmark files remain pytest-benchmark suites.  This adapter lets
the module-validation verifier execute one representative public workload without
pretending that process exit alone proves the budget was met.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean
from time import perf_counter_ns
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

_MAX_SMOKE_ITERATIONS = 256
_NANOSECONDS_PER_SECOND = 1_000_000_000
_ResultT = TypeVar("_ResultT")


@dataclass(frozen=True, slots=True)
class _TimingStatistics:
    mean: float


@dataclass(frozen=True, slots=True)
class _BenchmarkStatistics:
    stats: _TimingStatistics


class SmokeBenchmark:
    """Minimal fixture-compatible timer for ordinary ``benchmark(...)`` calls."""

    def __init__(self, iterations: int) -> None:
        if type(iterations) is not int or not 1 <= iterations <= _MAX_SMOKE_ITERATIONS:
            raise ValueError("iterations must be an integer between 1 and 256")  # noqa: TRY003
        self._iterations = iterations
        self.extra_info: dict[str, object] = {}
        self.samples_ns: tuple[int, ...] = ()
        self.stats: _BenchmarkStatistics | None = None

    def __call__(
        self,
        operation: Callable[..., _ResultT],
        *args: object,
        **kwargs: object,
    ) -> _ResultT:
        samples: list[int] = []
        result: _ResultT | None = None
        for _ in range(self._iterations):
            started = perf_counter_ns()
            result = operation(*args, **kwargs)
            samples.append(perf_counter_ns() - started)
        self.samples_ns = tuple(samples)
        self.stats = _BenchmarkStatistics(
            stats=_TimingStatistics(mean=fmean(samples) / _NANOSECONDS_PER_SECOND)
        )
        return result  # type: ignore[return-value]  # iterations is strictly positive.


def run_pytest_benchmark(
    *,
    module_id: str,
    workload: Callable[[Any], None],
    iterations: int,
    mean_budget_seconds: float,
) -> dict[str, object]:
    """Execute and normalize one genuine legacy benchmark workload."""

    if not math.isfinite(mean_budget_seconds) or mean_budget_seconds <= 0:
        raise ValueError("mean benchmark budget must be positive and finite")  # noqa: TRY003
    benchmark = SmokeBenchmark(iterations)
    assertion_passed = True
    try:
        workload(benchmark)
    except AssertionError:
        if benchmark.stats is None:
            raise
        assertion_passed = False
    if benchmark.stats is None or not benchmark.samples_ns:
        raise RuntimeError("benchmark workload did not execute a timed operation")  # noqa: TRY003
    ordered = sorted(benchmark.samples_ns)
    p95_index = min(len(ordered) - 1, (95 * len(ordered) - 1) // 100)
    mean_ns = fmean(benchmark.samples_ns)
    mean_budget_ns = int(mean_budget_seconds * _NANOSECONDS_PER_SECOND)
    return {
        "module_id": module_id,
        "workload": workload.__name__,
        "iterations": iterations,
        "mean_ns": mean_ns,
        "p95_ns": ordered[p95_index],
        "mean_budget_ns": mean_budget_ns,
        "assertion_passed": assertion_passed,
        "passed": assertion_passed and mean_ns <= mean_budget_ns,
    }


__all__ = ["SmokeBenchmark", "run_pytest_benchmark"]

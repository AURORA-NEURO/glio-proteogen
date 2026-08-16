"""Locked microbenchmark wrapper for M20-02."""

from __future__ import annotations

from statistics import median
from time import perf_counter_ns
from typing import TYPE_CHECKING, Any

from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_02_cross_source_alignment_reconciliation import (  # noqa: E501
    M2002Engine,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def run_benchmark(factory: Callable[..., Any], iterations: int = 10) -> dict[str, object]:
    """Measure strict resolution without I/O or artifact traversal."""

    if iterations < 1:
        raise ValueError("iterations must be positive")  # noqa: TRY003
    engine = M2002Engine()
    request = factory()
    samples: list[int] = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = engine.resolve(request)
        samples.append(perf_counter_ns() - started)
        if result.aligned_bundle is None:
            raise RuntimeError("benchmark fixture must be aligned")  # noqa: TRY003
    ordered = sorted(samples)
    return {
        "module": "GLIO-PROTEOGEN-M20-02",
        "iterations": iterations,
        "samples_ns": samples,
        "mean_ns": sum(samples) / len(samples),
        "median_ns": median(samples),
        "p95_ns": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "budget_mean_ns": 500_000_000,
        "budget_p95_ns": 750_000_000,
    }


__all__ = ["run_benchmark"]

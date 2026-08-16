"""Reproducible M11-03 construction benchmark wrapper."""

from __future__ import annotations

import json
from statistics import mean, median
from time import perf_counter_ns
from typing import Any

from evals.m11_03.run import request_for
from glio_proteogen.modules.c11_protein_native_subtype.m11_03_mechanistic_feature_constructor import (  # noqa: E501
    construct_variant_peptide_mechanistic_features,
)

_MAX_ITERATIONS = 1_000
_MEAN_BUDGET_NS = 2_000_000_000
_P95_BUDGET_NS = 3_000_000_000


class _InvalidBenchmarkIterationsError(ValueError):
    def __init__(self) -> None:
        super().__init__("iterations must be between 1 and 1000")


class _BenchmarkConstructionError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("benchmark fixture did not construct")


def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    if isinstance(iterations, bool) or iterations < 1 or iterations > _MAX_ITERATIONS:
        raise _InvalidBenchmarkIterationsError
    request = request_for({"case_id": "benchmark"})
    for _ in range(2):
        construct_variant_peptide_mechanistic_features(request)
    elapsed = []
    for _ in range(iterations):
        started = perf_counter_ns()
        result = construct_variant_peptide_mechanistic_features(request)
        elapsed.append(perf_counter_ns() - started)
        if result.status.value != "constructed":
            raise _BenchmarkConstructionError
    ordered = sorted(elapsed)
    p95 = ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)]
    return {
        "module_id": "GLIO-PROTEOGEN-M11-03",
        "iterations": iterations,
        "mean_ns": int(mean(elapsed)),
        "median_ns": int(median(elapsed)),
        "p95_ns": int(p95),
        "max_ns": max(elapsed),
        "mean_budget_ns": _MEAN_BUDGET_NS,
        "p95_budget_ns": _P95_BUDGET_NS,
        "passed": mean(elapsed) <= _MEAN_BUDGET_NS and p95 <= _P95_BUDGET_NS,
    }


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), indent=2, sort_keys=True))  # noqa: T201

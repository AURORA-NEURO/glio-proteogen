"""Executable evaluator and benchmark tests for M26-03."""

from __future__ import annotations

from typing import cast

from evals.m26_03.benchmark import run_benchmark
from evals.m26_03.evaluator import run_evaluator

_SCENARIO_COUNT = 7
_MEAN_BUDGET_NS = 500_000_000
_P95_BUDGET_NS = 750_000_000


def test_m2603_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["scenario_count"] == _SCENARIO_COUNT
    assert report["passed"] == report["scenario_count"]


def test_m2603_benchmark_stays_within_provisional_budget() -> None:
    report = run_benchmark(iterations=3)
    assert report["passed"] is True
    assert cast("int", report["mean_ns"]) <= _MEAN_BUDGET_NS
    assert cast("int", report["p95_ns"]) <= _P95_BUDGET_NS

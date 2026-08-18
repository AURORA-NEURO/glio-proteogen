"""Evaluator and benchmark tests for M20-05."""

from __future__ import annotations

from evals.m20_05.benchmark import run_benchmark
from evals.m20_05.evaluator import run_evaluator

_SCENARIO_COUNT = 8
_BENCHMARK_ITERATIONS = 3


def test_m20_05_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] == report["scenario_count"] == _SCENARIO_COUNT
    assert all(report["checks"].values())


def test_m20_05_locked_benchmark_within_budget() -> None:
    report = run_benchmark(iterations=_BENCHMARK_ITERATIONS)
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["passed"] is True

"""Evaluator and benchmark tests for M20-06."""

from __future__ import annotations

from evals.m20_06.benchmark import run_benchmark
from evals.m20_06.run import run

_SCENARIO_COUNT = 9
_BENCHMARK_ITERATIONS = 25


def test_m20_06_evaluator_matrix_passes() -> None:
    report = run()
    assert report["status"] == "PASS"
    assert report["executed_case_count"] == _SCENARIO_COUNT
    assert all(item["passed"] for item in report["checks"])


def test_m20_06_locked_benchmark_within_budget() -> None:
    report = run_benchmark()
    assert report.iterations == _BENCHMARK_ITERATIONS
    assert report.passed is True

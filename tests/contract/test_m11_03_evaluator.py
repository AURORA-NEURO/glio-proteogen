"""Evaluator and benchmark evidence tests for M11-03."""

from evals.m11_03.benchmark import run_benchmark
from evals.m11_03.run import run_evaluator

_CASE_COUNT = 7


def test_evaluator_fixture_is_complete_and_benchmark_is_within_budget() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == report["executed_cases"] == _CASE_COUNT
    assert report["passed_cases"] == _CASE_COUNT
    assert report["declared_case_ids"] == report["executed_case_ids"]
    benchmark = run_benchmark(10)
    assert benchmark["passed"] is True
    assert benchmark["mean_ns"] <= benchmark["mean_budget_ns"]
    assert benchmark["p95_ns"] <= benchmark["p95_budget_ns"]

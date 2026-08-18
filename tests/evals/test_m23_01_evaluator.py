"""Frozen M23-01 evaluator and benchmark tests."""

from typing import cast

from evals.m23_01.benchmark import run_benchmark
from evals.m23_01.run import EXPECTED_CASE_IDS, run_evaluation

_CASE_COUNT = 8
_BENCHMARK_ITERATIONS = 3


def test_frozen_evaluation_matrix_passes() -> None:
    report = run_evaluation()
    assert tuple(cast("list[str]", report["case_ids"])) == EXPECTED_CASE_IDS
    assert report["declared_cases"] == _CASE_COUNT
    assert report["executed_cases"] == _CASE_COUNT
    assert report["passed_cases"] == _CASE_COUNT
    assert report["passed"] is True


def test_locked_benchmark_stays_within_budgets() -> None:
    report = run_benchmark(iterations=_BENCHMARK_ITERATIONS)
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert cast("int", report["mean_ns"]) <= cast("int", report["mean_budget_ns"])
    assert cast("int", report["p95_ns"]) <= cast("int", report["p95_budget_ns"])
    assert report["passed"] is True

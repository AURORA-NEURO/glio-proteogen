"""Evaluator and benchmark regression tests for M08-07."""

from evals.m08_07.benchmark import run_benchmark
from evals.m08_07.run import run_evaluation


def test_evaluator_matrix_passes() -> None:
    report = run_evaluation()
    assert report.passed is True
    assert len(report.scenarios) == 8
    assert all(report.scenarios.values())


def test_benchmark_is_deterministic_and_within_budget() -> None:
    report = run_benchmark()
    assert report.passed is True
    assert report.iterations == 10
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns


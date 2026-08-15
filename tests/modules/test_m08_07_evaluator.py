"""Evaluator and benchmark regression tests for M08-07."""

from evals.m08_07.benchmark import run_benchmark
from evals.m08_07.run import run_evaluation

EXPECTED_SCENARIOS = 8
EXPECTED_ITERATIONS = 10


def test_evaluator_matrix_passes() -> None:
    report = run_evaluation()
    assert report.passed is True
    assert len(report.scenarios) == EXPECTED_SCENARIOS
    assert all(report.scenarios.values())


def test_benchmark_is_deterministic_and_within_budget() -> None:
    report = run_benchmark()
    assert report.passed is True
    assert report.iterations == EXPECTED_ITERATIONS
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns

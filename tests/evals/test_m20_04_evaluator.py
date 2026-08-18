"""Executable evaluator and benchmark checks for M20-04."""

from evals.m20_04.benchmark import run_benchmark
from evals.m20_04.run import evaluate

EXPECTED_CASES = 8
EXPECTED_ITERATIONS = 10
EXPECTED_COVERAGE = 100.0


def test_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report.passed is True
    assert report.scenario_count == EXPECTED_CASES
    assert report.adversarial_passed_count == EXPECTED_CASES
    assert report.adversarial_coverage_percent == EXPECTED_COVERAGE


def test_benchmark_is_deterministic_and_within_budget() -> None:
    report = run_benchmark()
    assert report.passed is True
    assert report.iterations == EXPECTED_ITERATIONS
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns

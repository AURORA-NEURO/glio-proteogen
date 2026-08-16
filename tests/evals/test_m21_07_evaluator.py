"""Executable M21-07 evaluator and benchmark checks."""

from evals.m21_07.benchmark import run_benchmark
from evals.m21_07.run import run_evaluator

EXPECTED_CASES = 8
EXPECTED_SCHEMAS = 7
EXPECTED_UNCERTAINTY_DIMENSIONS = 7
EXPECTED_ITERATIONS = 10


def test_m21_07_evaluator_passes_all_frozen_cases() -> None:
    result = run_evaluator()
    assert result["passed"] is True
    assert result["passed_cases"] == EXPECTED_CASES
    assert result["schema_count"] == EXPECTED_SCHEMAS
    assert result["uncertainty_dimensions"] == EXPECTED_UNCERTAINTY_DIMENSIONS


def test_m21_07_benchmark_is_within_locked_budgets() -> None:
    result = run_benchmark()
    assert result["iterations"] == EXPECTED_ITERATIONS
    assert result["passed"] is True

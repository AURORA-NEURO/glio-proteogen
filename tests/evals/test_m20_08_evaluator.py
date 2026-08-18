"""Executable M20-08 evaluator and benchmark checks."""

from evals.m20_08.benchmark import run_benchmark
from evals.m20_08.run import run_evaluator

_EXPECTED_CASES = 8
_EXPECTED_UNCERTAINTY_DIMENSIONS = 7
_EXPECTED_ITERATIONS = 10


def test_m20_08_evaluator_passes_all_frozen_cases() -> None:
    result = run_evaluator()
    assert result["passed"] is True
    assert result["passed_cases"] == _EXPECTED_CASES
    assert result["schema_count"] == _EXPECTED_CASES
    assert result["uncertainty_dimensions"] == _EXPECTED_UNCERTAINTY_DIMENSIONS


def test_m20_08_benchmark_is_within_locked_budgets() -> None:
    result = run_benchmark()
    assert result["iterations"] == _EXPECTED_ITERATIONS
    assert result["passed"] is True

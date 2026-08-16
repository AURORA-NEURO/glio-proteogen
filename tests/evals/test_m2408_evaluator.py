"""Executable M24-08 evaluator and benchmark checks."""

from evals.m24_08.benchmark import run_benchmark
from evals.m24_08.run import run_evaluator

_EXPECTED_CASES = 8
_EXPECTED_SCHEMA_COUNT = 10
_EXPECTED_UNCERTAINTY_DIMENSIONS = 7
_EXPECTED_ITERATIONS = 10


def test_m24_08_evaluator_passes_all_frozen_cases() -> None:
    result = run_evaluator()
    assert result["passed"] is True
    assert result["passed_cases"] == _EXPECTED_CASES
    assert result["schema_count"] == _EXPECTED_SCHEMA_COUNT
    assert result["uncertainty_dimensions"] == _EXPECTED_UNCERTAINTY_DIMENSIONS


def test_m24_08_benchmark_is_within_locked_budgets() -> None:
    result = run_benchmark()
    assert result["iterations"] == _EXPECTED_ITERATIONS
    assert result["passed"] is True

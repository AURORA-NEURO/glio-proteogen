"""Evaluator and benchmark regression tests for M12-08."""

# ruff: noqa: PLR2004

from evals.m12_08.benchmark import run_benchmark
from evals.m12_08.run import EXPECTED_CASE_IDS, run_evaluator


def test_locked_m1208_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == len(EXPECTED_CASE_IDS) == 8
    assert report["executed_cases"] == report["passed_cases"] == report["total_cases"]


def test_m1208_benchmark_respects_provisional_budgets() -> None:
    report = run_benchmark(3)
    assert report["iterations"] == 3
    assert report["passed"] is True

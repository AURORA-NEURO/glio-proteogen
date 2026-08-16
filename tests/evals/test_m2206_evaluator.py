"""Executable M22-06 evaluator and benchmark checks."""

# ruff: noqa: PLR2004

from evals.m22_06.benchmark import run_benchmark
from evals.m22_06.run import run_evaluator


def test_evaluator_fixture_passes() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["passed_cases"] == 9
    assert report["declared_cases"] == 9


def test_benchmark_budget_passes() -> None:
    report = run_benchmark(3)
    assert report["passed"] is True

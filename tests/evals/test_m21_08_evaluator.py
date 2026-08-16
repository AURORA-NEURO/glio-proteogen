"""Executable M21-08 evaluator and benchmark checks."""

# ruff: noqa: PLR2004

from evals.m21_08.benchmark import run_benchmark
from evals.m21_08.run import run_evaluator


def test_evaluator_fixture_passes() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["passed_cases"] == 10
    assert report["declared_cases"] == 10


def test_benchmark_budget_passes() -> None:
    report = run_benchmark(3)
    assert report["passed"] is True

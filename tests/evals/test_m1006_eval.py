"""Evaluator and benchmark regression tests for M10-06."""

# Evaluator inventory and iteration literals are deliberate assertions.
# ruff: noqa: PLR2004

from evals.m10_06.benchmark import run_benchmark
from evals.m10_06.run import evaluate


def test_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report["passed"] is True
    assert report["check_count"] == 7


def test_benchmark_respects_provisional_budgets() -> None:
    report = run_benchmark(iterations=3)
    assert report["passed"] is True
    assert report["iterations"] == 3

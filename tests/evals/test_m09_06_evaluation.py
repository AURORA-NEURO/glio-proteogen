"""Evaluator and benchmark tests for M09-06."""

# ruff: noqa: INP001

from __future__ import annotations

from evals.m09_06.benchmark import benchmark
from evals.m09_06.run import evaluate

_DIMENSION_COUNT = 7


def test_evaluation_matrix_passes() -> None:
    report = evaluate()
    assert report.passed is True
    assert report.seven_dimensions == _DIMENSION_COUNT
    assert report.replay_verified is True
    assert report.tamper_rejected is True


def test_benchmark_budget_passes() -> None:
    report = benchmark(iterations=3)
    assert report.passed is True
    assert report.dimension_count == _DIMENSION_COUNT

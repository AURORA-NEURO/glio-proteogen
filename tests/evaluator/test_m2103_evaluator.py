"""Evaluator and benchmark smoke tests for M21-03."""

import pytest
from evals.m21_03.benchmark import run_benchmark
from evals.m21_03.evaluator import run_evaluator


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] == report["scenario_count"]
    assert all(report["checks"].values())


def test_benchmark_rejects_non_positive_iterations() -> None:
    with pytest.raises(ValueError, match="positive"):
        run_benchmark(0)
    report = run_benchmark(1)
    assert report["passed"] is True

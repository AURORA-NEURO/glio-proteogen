"""Evaluator and benchmark evidence tests for M13-05."""

import pytest
from evals.m13_05.benchmark import run_benchmark
from evals.m13_05.run import EXPECTED_CASE_IDS, run_evaluator


def test_locked_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == len(EXPECTED_CASE_IDS)
    assert report["executed_cases"] == len(EXPECTED_CASE_IDS)
    assert report["passed_cases"] == len(EXPECTED_CASE_IDS)


def test_benchmark_is_bounded_and_deterministic() -> None:
    report = run_benchmark(iterations=3)
    assert report["iterations"] == 3
    assert report["passed"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]


def test_benchmark_rejects_non_positive_iterations() -> None:
    with pytest.raises(ValueError, match="positive"):
        run_benchmark(iterations=0)

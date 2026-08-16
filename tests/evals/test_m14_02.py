"""Locked M14-02 evaluator and benchmark evidence tests."""

# ruff: noqa: PLR2004

from evals.m14_02.benchmark import run_benchmark
from evals.m14_02.run import EXPECTED_CASE_IDS, run_evaluator


def test_m1402_evaluator_fixture_and_matrix_are_green() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == len(EXPECTED_CASE_IDS) == 9
    assert report["executed_cases"] == report["passed_cases"] == 9
    assert isinstance(report["fixture_digest"], str)


def test_m1402_benchmark_respects_provisional_budget() -> None:
    report = run_benchmark(3)
    assert report["iterations"] == 3
    assert report["passed"] is True
    assert isinstance(report["mean_ns"], int)
    assert isinstance(report["p95_ns"], int)
    assert isinstance(report["mean_budget_ns"], int)
    assert isinstance(report["p95_budget_ns"], int)
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]

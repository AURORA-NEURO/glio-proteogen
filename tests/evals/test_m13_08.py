"""Locked M13-08 evaluator and benchmark evidence tests."""

# ruff: noqa: PLR2004

from evals.m13_08.benchmark import run_benchmark
from evals.m13_08.run import EXPECTED_CASE_IDS, run_evaluator


def test_m1308_evaluator_fixture_and_matrix_are_green() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == len(EXPECTED_CASE_IDS) == 7
    assert report["executed_cases"] == report["passed_cases"] == 7
    assert (
        report["fixture_digest"]
        == "sha256:eb929387f8ebe0e28b2fe66e4baa0fde4e2ff35ae7a5b94fa54704551e97303e"
    )


def test_m1308_benchmark_respects_provisional_budget() -> None:
    report = run_benchmark(3)
    assert report["iterations"] == 3
    assert report["passed"] is True
    assert isinstance(report["mean_ns"], int)
    assert isinstance(report["mean_budget_ns"], int)
    assert isinstance(report["p95_ns"], int)
    assert isinstance(report["p95_budget_ns"], int)
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]

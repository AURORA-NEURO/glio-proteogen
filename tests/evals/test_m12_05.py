"""Locked M12-05 evaluator and benchmark evidence tests."""

from evals.m12_05.benchmark import run_benchmark
from evals.m12_05.run import EXPECTED_CASE_IDS, run_evaluator


def test_m1205_evaluator_fixture_and_matrix_are_green() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == len(EXPECTED_CASE_IDS) == 7
    assert report["executed_cases"] == report["passed_cases"] == 7
    assert report["fixture_digest"] == "sha256:1693c653b60132d289fd85ef672d049dfc41d383deea3c723d8177b9de6ce4db"


def test_m1205_benchmark_respects_provisional_budget() -> None:
    report = run_benchmark(3)
    assert report["iterations"] == 3
    assert report["passed"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]

"""Executable evaluator and benchmark evidence tests for M12-06."""

from evals.m12_06.benchmark import run_benchmark
from evals.m12_06.run import run_evaluation


def test_m1206_evaluator_fixture_passes() -> None:
    report = run_evaluation()
    assert report["passed"] is True
    assert report["declared_case_count"] == report["executed_case_count"]


def test_m1206_benchmark_is_deterministic_and_within_provisional_budget() -> None:
    report = run_benchmark(iterations=3)
    assert report.passed
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns

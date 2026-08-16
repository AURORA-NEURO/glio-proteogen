"""Executable evaluator and benchmark assertions for M17-01."""

from evals.m17_01.benchmark import run_benchmark
from evals.m17_01.run import evaluate


def test_m1701_evaluator_meets_adversarial_target() -> None:
    report = evaluate()

    assert report.passed is True
    assert report.adversarial_coverage_percent >= report.target_percent
    assert report.adversarial_passed_count == report.adversarial_case_count
    assert all(check.passed for check in report.checks)


def test_m1701_benchmark_is_deterministic_and_within_budget() -> None:
    report = run_benchmark()

    assert report.passed is True
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns
    assert report.request_digest.startswith("sha256:")
    assert report.result_digest.startswith("sha256:")

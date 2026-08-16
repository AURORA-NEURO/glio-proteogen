"""Evaluator and benchmark smoke tests for M19-07."""

from evals.m19_07.benchmark import run_benchmark
from evals.m19_07.run import evaluate


def test_m19_07_evaluator_passes() -> None:
    report = evaluate()
    assert report.passed
    assert report.adversarial_passed_count == report.adversarial_case_count


def test_m19_07_benchmark_is_deterministic_and_within_budget() -> None:
    report = run_benchmark()
    assert report.passed
    assert report.result_digest.startswith("sha256:")

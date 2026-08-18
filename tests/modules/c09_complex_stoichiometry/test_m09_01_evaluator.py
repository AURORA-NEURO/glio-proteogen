"""Evaluator and benchmark tests for M09-01."""

from evals.m09_01.benchmark import benchmark
from evals.m09_01.run import evaluate


def test_evaluator_matrix_passes() -> None:
    report = evaluate()

    assert report.passed
    assert report.replay_verified
    assert report.tamper_rejected
    assert report.deterministic
    assert report.valid_status == "valid"
    assert report.invalid_status == "invalid"
    assert report.missing_status == "abstained"
    assert report.unknown_expression_status == "abstained"


def test_benchmark_respects_provisional_budgets() -> None:
    report = benchmark(3)

    assert report.passed
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns

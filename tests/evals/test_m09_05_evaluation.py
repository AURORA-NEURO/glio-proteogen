"""Evaluator and benchmark tests for M09-05."""

# The fixture count is an explicit evaluator invariant.
# ruff: noqa: PLR2004

from evals.m09_05.benchmark import benchmark
from evals.m09_05.run import evaluate


def test_m09_05_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report.passed
    assert report.replay_verified
    assert report.tamper_rejected
    assert report.soft_ablation_visible


def test_m09_05_benchmark_is_within_provisional_budget() -> None:
    report = benchmark(3)
    assert report.passed
    assert report.constraint_count == 2

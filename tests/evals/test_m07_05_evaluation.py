"""Evaluator gates for M07-05."""

from evals.m07_05.benchmark import benchmark
from evals.m07_05.run import evaluate

_EXPECTED_CONSTRAINTS = 2
_EXPECTED_FEATURES = 2


def test_m07_05_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report.passed is True
    assert report.integrated_status == "integrated"
    assert report.hard_violation_status == "abstained"
    assert report.missing_feature_status == "abstained"
    assert report.replay_verified is True


def test_m07_05_benchmark_is_within_budget() -> None:
    report = benchmark(iterations=3)
    assert report.passed is True
    assert report.constraint_count == _EXPECTED_CONSTRAINTS
    assert report.feature_count == _EXPECTED_FEATURES

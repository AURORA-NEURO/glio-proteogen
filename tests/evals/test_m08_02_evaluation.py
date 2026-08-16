"""Evaluator gates for M08-02."""

from evals.m08_02.benchmark import benchmark
from evals.m08_02.run import evaluate

EXPECTED_FEATURES = 2
EXPECTED_SOURCES = 2


def test_m08_02_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report.passed is True
    assert report.constructed_status == "constructed"
    assert report.leakage_abstained_status == "abstained"
    assert report.duplicate_source_abstained_status == "abstained"
    assert report.lineage_complete is True
    assert report.leakage_checks_complete is True
    assert report.replay_verified is True


def test_m08_02_benchmark_is_within_budget() -> None:
    report = benchmark(iterations=3)
    assert report.passed is True
    assert report.feature_count == EXPECTED_FEATURES
    assert report.source_count == EXPECTED_SOURCES

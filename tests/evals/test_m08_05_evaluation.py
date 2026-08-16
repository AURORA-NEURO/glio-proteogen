"""Evaluator and benchmark regression checks for M08-05."""

import pytest
from evals.m08_05.benchmark import benchmark
from evals.m08_05.run import evaluate


def test_evaluator_matrix_passes() -> None:
    report = evaluate()

    assert report.passed
    assert report.replay_verified
    assert report.tamper_rejected
    assert report.deterministic


def test_benchmark_rejects_nonpositive_iterations() -> None:
    with pytest.raises(ValueError, match="positive"):
        benchmark(0)

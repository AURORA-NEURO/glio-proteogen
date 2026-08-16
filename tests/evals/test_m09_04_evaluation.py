"""Evaluator and benchmark regression checks for M09-04."""

import pytest
from evals.m09_04.benchmark import benchmark
from evals.m09_04.run import evaluate


def test_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report.passed
    assert report.replay_verified
    assert report.tamper_rejected
    assert report.deterministic
    assert report.uncertainty_explicit


def test_benchmark_rejects_nonpositive_iterations() -> None:
    with pytest.raises(ValueError, match="positive"):
        benchmark(0)

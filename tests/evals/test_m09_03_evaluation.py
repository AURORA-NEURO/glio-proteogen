"""Evaluator and benchmark gates for M09-03."""

import pytest
from evals.m09_03.benchmark import benchmark
from evals.m09_03.run import evaluate


def test_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report.passed
    assert report.replay_verified
    assert report.tamper_rejected
    assert report.deterministic
    assert report.uncertainty_explicit
    assert report.ownership_boundary_closed


def test_benchmark_rejects_nonpositive_iterations() -> None:
    with pytest.raises(ValueError, match="positive"):
        benchmark(0)

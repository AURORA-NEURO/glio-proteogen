"""Evaluator and benchmark regression checks for provisional M08-08."""

import pytest
from evals.m08_08.benchmark import benchmark
from evals.m08_08.run import evaluate


def test_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report.passed
    assert report.replay_verified
    assert report.tamper_rejected
    assert report.deterministic
    assert report.counter_evidence_count > 0
    assert report.reconstruction_count > 0


def test_benchmark_rejects_nonpositive_iterations() -> None:
    with pytest.raises(ValueError, match="positive"):
        benchmark(0)

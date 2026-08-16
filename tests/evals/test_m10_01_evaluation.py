"""Frozen evaluator matrix for M10-01."""

from evals.m10_01.evaluate import evaluate


def test_m10_01_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report["status"] == "passed"
    assert all(report["checks"].values())

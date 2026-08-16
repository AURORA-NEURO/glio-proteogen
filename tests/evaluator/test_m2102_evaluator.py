"""Evaluator smoke tests for M21-02."""

from evals.m21_02.evaluator import run_evaluator


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] == report["scenario_count"]
    assert all(report["checks"].values())

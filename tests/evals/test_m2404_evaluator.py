"""Evaluator assertions for provisional M24-04."""

from evals.m24_04.evaluator import run_evaluator


def test_m2404_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] == report["scenario_count"]
    assert all(report["checks"].values())

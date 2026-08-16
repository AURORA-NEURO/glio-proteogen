"""Evaluator and benchmark checks for M10-08."""

from evals.m10_08.benchmark import measure
from evals.m10_08.run import evaluate


def test_m1008_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report["passed"] is True
    assert all(report["checks"].values())  # type: ignore[union-attr]


def test_m1008_benchmark_stays_within_provisional_budgets() -> None:
    report = measure()
    assert report["passed"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]

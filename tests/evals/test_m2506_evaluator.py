"""Frozen M25-06 evaluator and benchmark checks."""

from evals.m25_06.benchmark import run_benchmark
from evals.m25_06.evaluator import run_evaluation

_SCENARIO_COUNT = 8
_ITERATIONS = 3


def test_evaluator_matrix_passes() -> None:
    report = run_evaluation()
    assert report["passed"] is True
    assert report["scenario_count"] == _SCENARIO_COUNT
    assert all(report["checks"].values())


def test_locked_benchmark_stays_within_budget() -> None:
    report = run_benchmark(_ITERATIONS)
    assert report["passed"] is True
    assert report["iterations"] == _ITERATIONS
    assert report["p95_ns"] < report["budget_p95_ns"]

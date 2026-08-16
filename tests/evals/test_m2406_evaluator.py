"""Evaluator and benchmark tests for provisional M24-06."""

from evals.m24_06.benchmark import run_benchmark
from evals.m24_06.evaluator import run_evaluation

_SCENARIO_COUNT = 13


def test_m2406_evaluator_matrix_passes() -> None:
    report = run_evaluation()
    assert report["passed"] is True
    assert report["scenario_count"] == _SCENARIO_COUNT
    assert all(report["checks"].values())


def test_m2406_benchmark_respects_provisional_budgets() -> None:
    report = run_benchmark(3)
    assert report["passed"] is True
    assert report["mean_ns"] <= report["budget_mean_ns"]
    assert report["p95_ns"] <= report["budget_p95_ns"]


__all__ = []

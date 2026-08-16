"""M21-01 evaluator and benchmark gates."""

from evals.m21_01.benchmark import run_benchmark
from evals.m21_01.evaluator import run_evaluator

_SCENARIO_COUNT = 6


def test_m2101_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["scenario_count"] == _SCENARIO_COUNT
    assert report["passed"] == report["scenario_count"]
    assert all(report["checks"].values())


def test_m2101_locked_benchmark_within_budget() -> None:
    report = run_benchmark(iterations=3)
    assert report["passed"] is True
    assert report["mean_ns"] <= report["budget_mean_ns"]
    assert report["p95_ns"] <= report["budget_p95_ns"]

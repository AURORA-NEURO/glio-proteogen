"""Evaluator and locked benchmark tests for M23-02."""

from evals.m23_02.benchmark import run_benchmark
from evals.m23_02.evaluator import run_evaluator

_ITERATIONS = 3


def test_evaluator_matrix_passes_all_scenarios() -> None:
    report = run_evaluator()

    assert report["passed"] == report["scenario_count"]
    assert all(report["checks"].values())
    assert report["fixture_counts"] == {
        "normal": 2,
        "missing": 2,
        "shifted": 2,
        "edge": 2,
        "adversarial": 2,
    }


def test_locked_benchmark_stays_within_budgets() -> None:
    report = run_benchmark(iterations=_ITERATIONS)

    assert report["iterations"] == _ITERATIONS
    assert report["passed"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]

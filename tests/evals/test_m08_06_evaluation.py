"""Executable evaluator and benchmark checks for M08-06."""

from evals.m08_06.benchmark import run_benchmark
from evals.m08_06.run import run_evaluation

_SCENARIOS = 5
_ITERATIONS = 3


def test_m0806_evaluator_passes_all_safety_cases() -> None:
    report = run_evaluation()
    assert report["passed"] is True
    assert report["scenario_count"] == _SCENARIOS
    assert all(case["passed"] for case in report["cases"])


def test_m0806_benchmark_respects_provisional_budgets() -> None:
    report = run_benchmark(iterations=_ITERATIONS)
    assert report["passed"] is True
    assert report["iterations"] == _ITERATIONS
    assert report["mean_ns"] < report["budget_ns"]
    assert report["p95_ns"] < report["p95_budget_ns"]

"""Evaluator and benchmark gates for M10-05."""

from evals.m10_05.benchmark import run_benchmark
from evals.m10_05.run import evaluate

EXPECTED_CHECKS = 8


def test_m1005_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report["module_id"] == "GLIO-PROTEOGEN-M10-05"
    assert report["passed"] is True
    assert report["check_count"] == EXPECTED_CHECKS
    assert all(item["passed"] is True for item in report["checks"])


def test_m1005_benchmark_is_deterministic_and_within_budget() -> None:
    report = run_benchmark(iterations=10)
    assert report["passed"] is True
    assert report["deterministic"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]

"""Evaluator and benchmark checks for provisional M07-03 evidence."""

from __future__ import annotations

from evals.m07_03.benchmark import run_benchmark
from evals.m07_03.run import evaluate

_CHECK_COUNT = 8
_BENCHMARK_ITERATIONS = 10


def test_locked_evaluator_passes_all_declared_checks() -> None:
    report = evaluate()
    assert report["module_id"] == "GLIO-PROTEOGEN-M07-03"
    assert report["passed"] is True
    assert report["check_count"] == _CHECK_COUNT
    assert all(item["passed"] is True for item in report["checks"])


def test_benchmark_passes_provisional_budgets() -> None:
    report = run_benchmark(_BENCHMARK_ITERATIONS)
    assert report["module_id"] == "GLIO-PROTEOGEN-M07-03"
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["passed"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]

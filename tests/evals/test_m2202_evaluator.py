"""Evaluator and benchmark evidence tests for provisional M22-02."""

from typing import cast

from evals.m22_02.benchmark import run_benchmark
from evals.m22_02.run import evaluate

_EXPECTED_CASES = 8
_EXPECTED_ITERATIONS = 10


def test_evaluator_passes_all_declared_cases() -> None:
    report = evaluate()
    assert report["module_id"] == "GLIO-PROTEOGEN-M22-02"
    assert report["declared_cases"] == _EXPECTED_CASES
    assert report["executed_cases"] == _EXPECTED_CASES
    assert report["passed_cases"] == _EXPECTED_CASES
    assert report["passed"] is True


def test_locked_benchmark_stays_within_budget() -> None:
    report = run_benchmark()
    assert report["iterations"] == _EXPECTED_ITERATIONS
    assert report["passed"] is True
    mean_ns = cast("int", report["mean_ns"])
    p95_ns = cast("int", report["p95_ns"])
    assert mean_ns <= cast("int", report["mean_budget_ns"])
    assert p95_ns <= cast("int", report["p95_budget_ns"])

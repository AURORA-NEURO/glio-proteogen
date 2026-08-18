"""Executable evaluator and benchmark assertions for M26-08."""

from __future__ import annotations

from evals.m26_08.benchmark import run_benchmark
from evals.m26_08.run import run_evaluator

EXPECTED_CASES = 10
EXPECTED_SCHEMAS = 10
EXPECTED_UNCERTAINTY_DIMENSIONS = 7
SHORT_BENCHMARK_ITERATIONS = 3


def test_m2608_evaluator_is_complete() -> None:
    report = run_evaluator()

    assert report["passed"] is True
    assert report["declared_cases"] == EXPECTED_CASES
    assert report["passed_cases"] == EXPECTED_CASES
    assert report["schema_count"] == EXPECTED_SCHEMAS
    assert report["uncertainty_dimensions"] == EXPECTED_UNCERTAINTY_DIMENSIONS


def test_m2608_benchmark_respects_locked_budget() -> None:
    report = run_benchmark(iterations=SHORT_BENCHMARK_ITERATIONS)

    assert report["passed"] is True
    assert report["iterations"] == SHORT_BENCHMARK_ITERATIONS

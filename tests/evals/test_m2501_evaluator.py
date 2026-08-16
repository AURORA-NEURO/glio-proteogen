"""Evaluator and benchmark checks for M25-01."""

from evals.m25_01.benchmark import run_benchmark
from evals.m25_01.evaluator import run_evaluator

_SCENARIO_COUNT = 8
_BENCHMARK_ITERATIONS = 3


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()

    assert report["passed"] is True
    assert report["scenario_count"] == _SCENARIO_COUNT
    assert report["passed_count"] == _SCENARIO_COUNT


def test_locked_benchmark_passes() -> None:
    report = run_benchmark(iterations=3)

    assert report["passed"] is True
    assert report["iterations"] == _BENCHMARK_ITERATIONS

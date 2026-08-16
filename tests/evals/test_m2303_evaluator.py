from __future__ import annotations

from evals.m23_03.benchmark import run_benchmark
from evals.m23_03.evaluator import run_evaluator

_EVALUATOR_SCENARIOS = 11
_BENCHMARK_ITERATIONS = 3


def test_m2303_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] == report["scenario_count"] == _EVALUATOR_SCENARIOS


def test_m2303_locked_benchmark_passes() -> None:
    report = run_benchmark(iterations=_BENCHMARK_ITERATIONS)
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["passed"] is True

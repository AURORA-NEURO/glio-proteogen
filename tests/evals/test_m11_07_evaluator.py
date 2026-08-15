"""Evaluator and benchmark assertions for M11-07."""

from evals.m11_07.benchmark import run_benchmark
from evals.m11_07.run import run_evaluator

_MATRIX_CASES = 6
_BENCHMARK_ITERATIONS = 3


def test_frozen_m11_07_matrix_passes() -> None:
    report = run_evaluator()
    assert report["fixture_digest"] == (
        "sha256:551b93ed5371820c247e23b1e4ecb3d9c6d1caa0c137874470a72e420839908c"
    )
    assert report["declared_cases"] == _MATRIX_CASES
    assert report["executed_cases"] == _MATRIX_CASES
    assert report["all_passed"] is True


def test_benchmark_has_budget_and_deterministic_shape() -> None:
    report = run_benchmark(iterations=_BENCHMARK_ITERATIONS)
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert len(report["samples_ns"]) == _BENCHMARK_ITERATIONS
    assert report["within_budget"] is True

"""Evaluator and benchmark assertions for M13-07."""

from evals.m13_07.benchmark import run_benchmark
from evals.m13_07.run import run_evaluator

_MATRIX_CASES = 6
_BENCHMARK_ITERATIONS = 3


def test_frozen_m13_07_matrix_passes() -> None:
    report = run_evaluator()
    assert report["fixture_digest"] == (
        "sha256:284c26a62ad62de735eb8de1497612dd1d98acb2bfd551796d80f3b0705e064c"
    )
    assert report["declared_cases"] == _MATRIX_CASES
    assert report["executed_cases"] == _MATRIX_CASES
    assert report["all_passed"] is True


def test_benchmark_has_budget_and_deterministic_shape() -> None:
    report = run_benchmark(iterations=_BENCHMARK_ITERATIONS)
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert len(report["samples_ns"]) == _BENCHMARK_ITERATIONS
    assert report["within_budget"] is True

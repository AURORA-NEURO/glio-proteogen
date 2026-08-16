"""Evaluator and benchmark tests for M25-03."""

from evals.m25_03.benchmark import run_benchmark
from evals.m25_03.evaluator import evaluate

_CHECK_COUNT = 9
_BENCHMARK_ITERATIONS = 3


def test_m2503_evaluator_matrix_passes() -> None:
    checks = evaluate()

    assert len(checks) == _CHECK_COUNT
    assert all(check.passed for check in checks), checks


def test_m2503_locked_benchmark_is_within_budget() -> None:
    report = run_benchmark(iterations=_BENCHMARK_ITERATIONS)

    assert report.iterations == _BENCHMARK_ITERATIONS
    assert len(report.samples_ns) == _BENCHMARK_ITERATIONS
    assert report.passed is True
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns

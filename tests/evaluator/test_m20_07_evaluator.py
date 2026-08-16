"""Evaluator and benchmark checks for M20-07."""

from evals.m20_07.benchmark import run_benchmark
from evals.m20_07.run import ADVERSARIAL_CASE_COUNT, EXPECTED_CASE_COUNT, run

_BENCHMARK_ITERATIONS = 25


def test_m20_07_evaluator_matrix_passes() -> None:
    report = run()
    assert report["status"] == "PASS"
    assert report["declared_case_count"] == EXPECTED_CASE_COUNT
    assert report["executed_case_count"] == EXPECTED_CASE_COUNT
    assert report["adversarial_case_count"] == ADVERSARIAL_CASE_COUNT


def test_m20_07_benchmark_is_within_provisional_budget() -> None:
    report = run_benchmark()
    assert report.passed
    assert report.iterations == _BENCHMARK_ITERATIONS
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns

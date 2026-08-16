"""Executable M11-05 evaluator and benchmark evidence tests."""

from evals.m11_05.benchmark import run_benchmark
from evals.m11_05.run import run_evaluator

EXPECTED_CASES = 8
BENCHMARK_ITERATIONS = 3


def test_evaluator_fixture_is_complete_and_passes() -> None:
    report = run_evaluator()
    assert report.module_id == "GLIO-PROTEOGEN-M11-05"
    assert report.declared_case_count == EXPECTED_CASES
    assert report.executed_case_count == EXPECTED_CASES
    assert report.passed_case_count == EXPECTED_CASES
    assert report.passed is True
    assert all(check.passed for check in report.checks)


def test_benchmark_is_inside_provisional_budget() -> None:
    report = run_benchmark(BENCHMARK_ITERATIONS)
    assert report.iterations == BENCHMARK_ITERATIONS
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns
    assert report.passed is True

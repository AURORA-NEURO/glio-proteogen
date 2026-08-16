"""Executable evaluator and benchmark tests for M18-04."""

from __future__ import annotations

from evals.m18_04.benchmark import run_benchmark
from evals.m18_04.run import evaluate

_SCENARIO_COUNT = 8
_ADVERSARIAL_PASS_COUNT = 8
_COVERAGE_TARGET = 95.0
_BENCHMARK_ITERATIONS = 10


def test_evaluator_passes_all_declared_scenarios() -> None:
    report = evaluate()
    assert report.passed is True
    assert report.module_id == "GLIO-PROTEOGEN-M18-04"
    assert report.scenario_count == _SCENARIO_COUNT
    assert report.adversarial_passed_count == _ADVERSARIAL_PASS_COUNT
    assert report.adversarial_coverage_percent >= _COVERAGE_TARGET


def test_benchmark_is_deterministic_and_within_provisional_budget() -> None:
    report = run_benchmark()
    assert report.passed is True
    assert report.iterations == _BENCHMARK_ITERATIONS
    assert report.request_digest.startswith("sha256:")
    assert report.result_digest.startswith("sha256:")

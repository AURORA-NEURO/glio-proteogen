"""Evaluator and benchmark tests for M18-01."""

from __future__ import annotations

from evals.m18_01.benchmark import run_benchmark
from evals.m18_01.run import evaluate

_SCENARIO_COUNT = 8
_COVERAGE_PERCENT = 100.0
_ITERATION_COUNT = 10


def test_m18_01_evaluator_passes_declared_matrix() -> None:
    report = evaluate()
    assert report.passed is True
    assert report.scenario_count == _SCENARIO_COUNT
    assert report.adversarial_passed_count == _SCENARIO_COUNT
    assert report.adversarial_coverage_percent == _COVERAGE_PERCENT


def test_m18_01_benchmark_is_deterministic_and_bounded() -> None:
    report = run_benchmark()
    assert report.passed is True
    assert report.iterations == _ITERATION_COUNT
    assert report.result_digest.startswith("sha256:")

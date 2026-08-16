"""Executable evaluator and benchmark gates for M18-07."""

# ruff: noqa: INP001, PLR2004

from __future__ import annotations

from evals.m18_07.benchmark import run_benchmark
from evals.m18_07.run import evaluate


def test_m1807_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert report.passed
    assert report.scenario_count == 8
    assert report.adversarial_passed_count == 8
    assert report.adversarial_coverage_percent == 100.0


def test_m1807_benchmark_is_deterministic_and_within_budget() -> None:
    report = run_benchmark()
    assert report.passed
    assert report.iterations == 10
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns

"""Evaluator and locked benchmark tests for provisional M22-07."""

from __future__ import annotations

from evals.m22_07.benchmark import run_benchmark
from evals.m22_07.evaluator import run_evaluator


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] == report["scenario_count"]
    assert report["fixture_result_digest"].startswith("sha256:")


def test_locked_benchmark_stays_within_provisional_budget() -> None:
    report = run_benchmark(iterations=3)
    assert report["passed"] is True
    assert report["mean_ns"] <= report["budget_mean_ns"]
    assert report["p95_ns"] <= report["budget_p95_ns"]

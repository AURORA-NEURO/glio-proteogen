"""Locked evaluator and benchmark tests for provisional M12-07."""

from __future__ import annotations

from evals.m12_07.benchmark import run_benchmark
from evals.m12_07.run import EXPECTED_CASE_IDS, run_evaluator


def test_m1207_evaluator_executes_every_locked_case() -> None:
    report = run_evaluator()
    assert report.passed is True
    assert report.declared_case_ids == EXPECTED_CASE_IDS
    assert report.executed_case_ids == EXPECTED_CASE_IDS
    assert all(item.passed for item in report.checks)


def test_m1207_benchmark_is_inside_provisional_budgets() -> None:
    report = run_benchmark(iterations=3)
    assert report.passed is True
    assert report.mean_ns <= report.mean_budget_ns
    assert report.p95_ns <= report.p95_budget_ns

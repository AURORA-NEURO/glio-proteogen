"""Evaluator and benchmark tests for M20-02."""

from __future__ import annotations

from evals.m20_02.benchmark import run_benchmark
from evals.m20_02.run import run_evaluation

from tests.modules.c17_metabolomic_lipidomic_integration.test_m20_02_engine import _request

SCENARIO_COUNT = 3


def test_m20_02_evaluator_matrix_and_replay() -> None:
    report = run_evaluation(_request)
    assert report["scenario_count"] == SCENARIO_COUNT
    assert report["passed_count"] == SCENARIO_COUNT
    assert report["replay_count"] == SCENARIO_COUNT


def test_m20_02_locked_benchmark_is_within_budget() -> None:
    report = run_benchmark(_request, iterations=3)
    assert report["iterations"] == SCENARIO_COUNT
    assert report["mean_ns"] < report["budget_mean_ns"]
    assert report["p95_ns"] < report["budget_p95_ns"]

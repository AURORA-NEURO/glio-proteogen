"""Evaluator and benchmark gates for M26-06."""

from __future__ import annotations

from evals.m26_06.benchmark import benchmark
from evals.m26_06.run import run_evaluator

_SCENARIO_COUNT = 6
_BENCHMARK_ITERATIONS = 10


def test_security_evaluator_matrix_is_safe_and_replay_verified() -> None:
    report = run_evaluator()
    assert report["module"] == "M26-06"
    assert report["scenario_count"] == _SCENARIO_COUNT
    assert report["passed"] == _SCENARIO_COUNT
    records = report["records"]
    assert records[0]["outcome"] == "evaluated"
    assert records[0]["replay_verified"] is True
    assert records[1]["outcome"] == "abstained"
    assert records[2]["outcome"] == "abstained"
    assert records[4]["outcome"] == "authorization_rejected"


def test_locked_benchmark_stays_within_security_budgets() -> None:
    report = benchmark(_BENCHMARK_ITERATIONS)
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["mean_ns"] < report["budget_mean_ns"]
    assert report["p95_ns"] < report["budget_p95_ns"]

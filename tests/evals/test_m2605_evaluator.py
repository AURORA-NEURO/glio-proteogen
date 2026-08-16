"""Evaluator and locked benchmark tests for M26-05."""

from __future__ import annotations

from benchmarks.m26_05_telemetry import run_benchmark
from evals.m26_05.evaluate import evaluate

_SCENARIO_COUNT = 7
_BENCHMARK_ITERATIONS = 3


def test_m2605_evaluator_all_scenarios_pass() -> None:
    report = evaluate()
    assert report["moduleId"] == "GLIO-PROTEOGEN-M26-05"
    assert report["allPassed"] is True
    assert report["passed"] == report["total"] == _SCENARIO_COUNT


def test_m2605_benchmark_respects_provisional_budget() -> None:
    report = run_benchmark(_BENCHMARK_ITERATIONS)
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["budgetPassed"] is True
    assert report["meanNs"] <= report["budgetsNs"]["mean"]

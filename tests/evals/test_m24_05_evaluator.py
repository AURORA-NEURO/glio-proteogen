"""Evaluator and benchmark tests for provisional M24-05."""

from __future__ import annotations

import runpy
from typing import cast

import pytest
from evals.m24_05.benchmark import run_benchmark
from evals.m24_05.evaluator import run_evaluator

EXPECTED_ITERATIONS = 10
EXPECTED_SCENARIOS = 13


def test_evaluator_passes_all_declared_scenarios() -> None:
    report = run_evaluator()
    assert report["module_id"] == "GLIO-PROTEOGEN-M24-05"
    assert report["scenario_count"] == EXPECTED_SCENARIOS
    assert report["passed"] is True
    assert cast("str", report["fixture_result_digest"]).startswith("sha256:")


def test_locked_benchmark_stays_within_budget() -> None:
    report = run_benchmark()
    assert report["iterations"] == EXPECTED_ITERATIONS
    assert report["passed"] is True
    assert cast("int", report["mean_ns"]) <= cast("int", report["mean_budget_ns"])
    assert cast("int", report["p95_ns"]) <= cast("int", report["p95_budget_ns"])


def test_evaluator_and_benchmark_entrypoints_execute() -> None:
    for module in ("evals.m24_05.evaluator", "evals.m24_05.benchmark"):
        with pytest.raises(SystemExit) as error:
            runpy.run_module(module, run_name="__main__")
        assert error.value.code == 0

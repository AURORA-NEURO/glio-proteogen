"""Evaluator and benchmark evidence tests for provisional M22-02."""

import runpy
from typing import cast

import pytest
from evals.m22_02.benchmark import run_benchmark
from evals.m22_02.run import evaluate

_EXPECTED_CASES = 8
_EXPECTED_ITERATIONS = 10


def test_evaluator_passes_all_declared_cases() -> None:
    report = evaluate()
    assert report["module_id"] == "GLIO-PROTEOGEN-M22-02"
    assert report["declared_cases"] == _EXPECTED_CASES
    assert report["executed_cases"] == _EXPECTED_CASES
    assert report["passed_cases"] == _EXPECTED_CASES
    assert report["passed"] is True


def test_locked_benchmark_stays_within_budget() -> None:
    report = run_benchmark()
    assert report["iterations"] == _EXPECTED_ITERATIONS
    assert report["passed"] is True
    mean_ns = cast("int", report["mean_ns"])
    p95_ns = cast("int", report["p95_ns"])
    assert mean_ns <= cast("int", report["mean_budget_ns"])
    assert p95_ns <= cast("int", report["p95_budget_ns"])


def test_evaluator_and_benchmark_entrypoints_execute() -> None:
    for module in ("evals.m22_02.run", "evals.m22_02.benchmark"):
        with pytest.raises(SystemExit) as error:
            runpy.run_module(module, run_name="__main__")
        assert error.value.code == 0

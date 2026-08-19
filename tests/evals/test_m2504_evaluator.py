"""Frozen evaluator and benchmark entrypoint tests for M25-04."""

from __future__ import annotations

import json
import runpy
import sys

import pytest
from evals.m25_04.benchmark import run_benchmark
from evals.m25_04.evaluator import run_evaluator

_BENCHMARK_ITERATIONS = 3


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["scenario_count"] == report["adversarial_passed_count"]


def test_benchmark_passes_locked_budget() -> None:
    report = run_benchmark(_BENCHMARK_ITERATIONS)
    assert report["passed"] is True
    assert report["iterations"] == _BENCHMARK_ITERATIONS


def test_evaluator_and_benchmark_entrypoints_execute(capsys) -> None:  # type: ignore[no-untyped-def]
    # The imported callables above intentionally exercise the library path.  Remove
    # those modules before the separate ``runpy`` entrypoint check so Python does
    # not emit a stale-module warning or mask a broken executable surface.
    sys.modules.pop("evals.m25_04.evaluator", None)
    sys.modules.pop("evals.m25_04.benchmark", None)
    with pytest.raises(SystemExit) as evaluator_exit:
        runpy.run_module("evals.m25_04.evaluator", run_name="__main__")
    evaluator = json.loads(capsys.readouterr().out)
    with pytest.raises(SystemExit) as benchmark_exit:
        runpy.run_module("evals.m25_04.benchmark", run_name="__main__")
    benchmark = json.loads(capsys.readouterr().out)
    assert evaluator_exit.value.code == 0
    assert benchmark_exit.value.code == 0
    assert evaluator["passed"] is True
    assert benchmark["passed"] is True

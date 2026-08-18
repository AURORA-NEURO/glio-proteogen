"""Evaluator and benchmark evidence checks for M06-08."""

from __future__ import annotations

import json
from pathlib import Path

from evals.m06_08.benchmark import run_benchmark
from evals.m06_08.run import evaluate

_CHECK_COUNT = 8
_BENCHMARK_ITERATIONS = 10


def test_locked_evaluator_passes_all_declared_scenarios() -> None:
    report = evaluate()
    assert report["module_id"] == "GLIO-PROTEOGEN-M06-08"
    assert report["passed"] is True
    assert report["check_count"] == _CHECK_COUNT
    assert all(item["passed"] is True for item in report["checks"])


def test_benchmark_passes_declared_provisional_budgets() -> None:
    report = run_benchmark(_BENCHMARK_ITERATIONS)
    assert report["module_id"] == "GLIO-PROTEOGEN-M06-08"
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["passed"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]


def test_fixture_manifest_is_bound_to_authority() -> None:
    root = Path(__file__).parents[2]
    manifest = json.loads((root / "tests/fixtures/m06_08/manifest.json").read_text())
    scenarios = json.loads((root / "tests/fixtures/m06_08/scenarios.json").read_text())
    assert manifest["module_id"] == scenarios["module_id"]
    assert manifest["dossier_lines"] == "2144-2184"
    assert len(scenarios["scenarios"]) == manifest["scenario_count"]

"""Evaluator and benchmark evidence tests for M13-05."""

import json
import sys
from pathlib import Path

import pytest
from evals.m13_05 import benchmark, run
from evals.m13_05.benchmark import run_benchmark
from evals.m13_05.run import EXPECTED_CASE_IDS, run_evaluator

_BENCHMARK_ITERATIONS = 3


def test_locked_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared_cases"] == len(EXPECTED_CASE_IDS)
    assert report["executed_cases"] == len(EXPECTED_CASE_IDS)
    assert report["passed_cases"] == len(EXPECTED_CASE_IDS)


def test_benchmark_is_bounded_and_deterministic() -> None:
    report = run_benchmark(iterations=_BENCHMARK_ITERATIONS)
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["passed"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]


def test_benchmark_rejects_non_positive_iterations() -> None:
    with pytest.raises(ValueError, match="positive"):
        run_benchmark(iterations=0)


def test_cli_entry_points_emit_machine_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["m13-05-eval", "--json"])
    assert run.main() == 0
    monkeypatch.setattr(sys, "argv", ["m13-05-benchmark", "--iterations", "1"])
    assert benchmark.main() == 0


def test_evaluator_rejects_fixture_case_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps({"cases": []}), encoding="utf-8")
    monkeypatch.setattr(run, "SCENARIO_PATH", path)
    with pytest.raises(ValueError, match="case IDs"):
        run_evaluator()

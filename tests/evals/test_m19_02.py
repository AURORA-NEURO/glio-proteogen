"""Evaluator and benchmark tests for M19-02."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m19_02 import benchmark, run
from evals.m19_02.benchmark import run_benchmark
from evals.m19_02.run import evaluate

if TYPE_CHECKING:
    from pathlib import Path

_SCENARIO_COUNT = 8
_COVERAGE_PERCENT = 100.0
_ITERATION_COUNT = 10


def test_m19_02_evaluator_passes_declared_matrix() -> None:
    report = evaluate()
    assert report.passed is True
    assert report.scenario_count == _SCENARIO_COUNT
    assert report.adversarial_passed_count == _SCENARIO_COUNT
    assert report.adversarial_coverage_percent == _COVERAGE_PERCENT


def test_m19_02_benchmark_is_deterministic_and_bounded() -> None:
    report = run_benchmark()
    assert report.passed is True
    assert report.iterations == _ITERATION_COUNT
    assert report.result_digest.startswith("sha256:")


def test_m19_02_command_entrypoints_write_reproducible_reports(tmp_path: Path) -> None:
    evaluation_path = tmp_path / "evaluation.json"
    benchmark_path = tmp_path / "benchmark.json"
    assert run.main(["--output", str(evaluation_path)]) == 0
    assert benchmark.main(["--output", str(benchmark_path)]) == 0
    assert '"passed": true' in evaluation_path.read_text(encoding="utf-8")
    assert '"passed": true' in benchmark_path.read_text(encoding="utf-8")


def test_m19_02_scenario_builder_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown M19-02"):
        run._scenario("not-a-scenario")

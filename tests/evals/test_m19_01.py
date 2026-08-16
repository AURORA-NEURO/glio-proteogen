"""Evaluator and benchmark tests for M19-01."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m19_01 import benchmark, run
from evals.m19_01.benchmark import run_benchmark
from evals.m19_01.run import evaluate

if TYPE_CHECKING:
    from pathlib import Path

_SCENARIO_COUNT = 9
_ADVERSARIAL_COUNT = 10
_COVERAGE_PERCENT = 100.0
_ITERATION_COUNT = 25


def test_m19_01_evaluator_passes_declared_matrix() -> None:
    report = evaluate()
    assert report.passed is True
    assert report.scenario_count == _SCENARIO_COUNT
    assert report.adversarial_passed_count == _ADVERSARIAL_COUNT
    assert report.adversarial_coverage_percent == _COVERAGE_PERCENT


def test_m19_01_benchmark_is_deterministic_and_bounded() -> None:
    report = run_benchmark()
    assert report.passed is True
    assert report.iterations == _ITERATION_COUNT
    assert report.result_digest.startswith("sha256:")
    assert report.replay_verified is True


def test_m19_01_command_entrypoints_write_reproducible_reports(tmp_path: Path) -> None:
    evaluation_path = tmp_path / "evaluation.json"
    benchmark_path = tmp_path / "benchmark.json"
    assert run.main(["--output", str(evaluation_path)]) == 0
    assert benchmark.main(["--output", str(benchmark_path)]) == 0
    assert '"passed": true' in evaluation_path.read_text(encoding="utf-8")
    assert '"passed": true' in benchmark_path.read_text(encoding="utf-8")


def test_m19_01_scenario_builder_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown M19-01"):
        run._scenario("not-a-scenario")

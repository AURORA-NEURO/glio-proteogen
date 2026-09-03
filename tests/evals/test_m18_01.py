"""Evaluator and benchmark tests for M18-01."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from evals.m18_01 import run
from evals.m18_01.run import evaluate

_SCENARIO_COUNT = 8
_COVERAGE_PERCENT = 100.0
_ITERATION_COUNT = 10
_BENCHMARK_TIMEOUT_SECONDS = 30


def _run_benchmark_fresh(output_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the wall-clock gate outside the coverage-traced pytest process."""
    root = Path(__file__).resolve().parents[2]
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("COV_CORE_", "COVERAGE_"))
    }
    return subprocess.run(  # noqa: S603 - fixed interpreter and repository module.
        [
            sys.executable,
            "-m",
            "evals.m18_01.benchmark",
            "--output",
            str(output_path),
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=_BENCHMARK_TIMEOUT_SECONDS,
        check=False,
    )


def test_m18_01_evaluator_passes_declared_matrix() -> None:
    report = evaluate()
    assert report.passed is True
    assert report.scenario_count == _SCENARIO_COUNT
    assert report.adversarial_passed_count == _SCENARIO_COUNT
    assert report.adversarial_coverage_percent == _COVERAGE_PERCENT


def test_m18_01_benchmark_is_deterministic_and_bounded(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    completed = _run_benchmark_fresh(benchmark_path)
    details = completed.stderr or completed.stdout
    assert completed.returncode == 0, details
    report = json.loads(benchmark_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["iterations"] == _ITERATION_COUNT
    assert report["result_digest"].startswith("sha256:")


def test_m18_01_command_entrypoints_write_reproducible_reports(tmp_path: Path) -> None:
    evaluation_path = tmp_path / "evaluation.json"
    benchmark_path = tmp_path / "benchmark.json"
    assert run.main(["--output", str(evaluation_path)]) == 0
    completed = _run_benchmark_fresh(benchmark_path)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert '"passed": true' in evaluation_path.read_text(encoding="utf-8")
    assert '"passed": true' in benchmark_path.read_text(encoding="utf-8")


def test_m18_01_scenario_builder_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown M18-01"):
        run._scenario("not-a-scenario")

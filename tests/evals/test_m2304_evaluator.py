"""Executable M23-04 evaluator and benchmark checks."""

import subprocess
import sys
from pathlib import Path

from evals.m23_04.benchmark import run_benchmark
from evals.m23_04.run import run_evaluator

_EXPECTED_CASES = 8
_EXPECTED_UNCERTAINTY_DIMENSIONS = 7
_EXPECTED_ITERATIONS = 10


def test_m23_04_evaluator_passes_all_frozen_cases() -> None:
    result = run_evaluator()
    assert result["passed"] is True
    assert result["passed_cases"] == _EXPECTED_CASES
    assert result["schema_count"] == _EXPECTED_CASES
    assert result["uncertainty_dimensions"] == _EXPECTED_UNCERTAINTY_DIMENSIONS


def test_m23_04_benchmark_is_within_locked_budgets() -> None:
    result = run_benchmark()
    assert result["iterations"] == _EXPECTED_ITERATIONS
    assert result["passed"] is True


def test_direct_benchmark_entrypoint_bootstraps_project_root() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(  # noqa: S603 - fixed local benchmark entrypoint
        [sys.executable, str(root / "evals/m23_04/benchmark.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert '"passed": true' in result.stdout

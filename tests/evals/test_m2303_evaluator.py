from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from evals.m23_03.benchmark import run_benchmark
from evals.m23_03.evaluator import run_evaluator

_EVALUATOR_SCENARIOS = 12
_BENCHMARK_ITERATIONS = 3


def test_m2303_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] == report["scenario_count"] == _EVALUATOR_SCENARIOS


def test_m2303_locked_benchmark_passes() -> None:
    report = run_benchmark(iterations=_BENCHMARK_ITERATIONS)
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["passed"] is True


def test_direct_evaluator_and_benchmark_entrypoints_bootstrap_project_root() -> None:
    root = Path(__file__).resolve().parents[2]
    evaluator = subprocess.run(  # noqa: S603 - fixed local evaluator entrypoint
        [sys.executable, str(root / "evals/m23_03/evaluator.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    benchmark = subprocess.run(  # noqa: S603 - fixed local benchmark entrypoint
        [sys.executable, str(root / "evals/m23_03/benchmark.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert '"passed": 12' in evaluator.stdout
    assert '"passed": true' in benchmark.stdout

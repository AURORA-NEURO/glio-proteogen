"""Evaluator and locked benchmark tests for provisional M23-07."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from evals.m23_07.benchmark import run_benchmark
from evals.m23_07.evaluator import run_evaluator


def test_evaluator_matrix_passes() -> None:
    report = run_evaluator()
    assert report["passed"] == report["scenario_count"]
    assert report["fixture_result_digest"].startswith("sha256:")


def test_locked_benchmark_stays_within_provisional_budget() -> None:
    report = run_benchmark(iterations=3)
    assert report["passed"] is True
    assert report["mean_ns"] <= report["budget_mean_ns"]
    assert report["p95_ns"] <= report["budget_p95_ns"]


def test_direct_evaluator_and_benchmark_entrypoints_bootstrap_project_root() -> None:
    root = Path(__file__).resolve().parents[2]
    evaluator = subprocess.run(  # noqa: S603 - fixed local evaluator entrypoint
        [sys.executable, str(root / "evals/m23_07/evaluator.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    benchmark = subprocess.run(  # noqa: S603 - fixed local benchmark entrypoint
        [sys.executable, str(root / "evals/m23_07/benchmark.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert '"passed": 11' in evaluator.stdout
    assert '"passed": true' in benchmark.stdout

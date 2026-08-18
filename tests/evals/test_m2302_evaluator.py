"""Evaluator and locked benchmark tests for M23-02."""

import subprocess
import sys
from pathlib import Path

from evals.m23_02.benchmark import run_benchmark
from evals.m23_02.evaluator import run_evaluator

_ITERATIONS = 3


def test_evaluator_matrix_passes_all_scenarios() -> None:
    report = run_evaluator()

    assert report["passed"] == report["scenario_count"]
    assert all(report["checks"].values())
    assert report["fixture_counts"] == {
        "normal": 2,
        "missing": 2,
        "shifted": 2,
        "edge": 2,
        "adversarial": 2,
    }


def test_locked_benchmark_stays_within_budgets() -> None:
    report = run_benchmark(iterations=_ITERATIONS)

    assert report["iterations"] == _ITERATIONS
    assert report["passed"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]


def test_direct_evaluator_and_benchmark_entrypoints_bootstrap_project_root() -> None:
    root = Path(__file__).resolve().parents[2]
    evaluator = subprocess.run(  # noqa: S603 - fixed local entrypoint under repository root
        [sys.executable, str(root / "evals/m23_02/evaluator.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    benchmark = subprocess.run(  # noqa: S603 - fixed local entrypoint under repository root
        [sys.executable, str(root / "evals/m23_02/benchmark.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert '"passed": 13' in evaluator.stdout
    assert '"passed": true' in benchmark.stdout

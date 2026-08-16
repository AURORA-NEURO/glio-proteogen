"""Executable evaluator and benchmark locks for M07-07."""

# ruff: noqa: INP001, PLR2004

from __future__ import annotations

from evals.m07_07.benchmark import benchmark
from evals.m07_07.run import evaluate


def test_evaluation_inventory_is_complete_and_passes() -> None:
    report = evaluate()
    assert report["declared"] == report["executed"] == 8
    assert report["passed"] == 8
    assert report["failed"] == 0
    assert report["status"] == "passed"


def test_benchmark_is_bounded_and_deterministic_in_shape() -> None:
    report = benchmark(iterations=3)
    assert report["iterations"] == 3
    assert len(report["timings_ns"]) == 3
    assert report["passed"] is True

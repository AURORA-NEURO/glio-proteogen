"""Evaluator matrix and benchmark tests for M24-07."""

from __future__ import annotations

from evals.m24_07.benchmark import run as run_benchmark
from evals.m24_07.evaluator import run_matrix

_SCENARIO_COUNT = 6
_SMOKE_ITERATIONS = 3


def test_locked_evaluator_matrix_passes() -> None:
    report = run_matrix()
    assert report["module"] == "M24-07"
    assert report["scenario_count"] == _SCENARIO_COUNT
    assert all(
        value is True
        for key, value in report["scenarios"].items()
        if key != "supported_result_digest"
    )
    assert str(report["scenarios"]["supported_result_digest"]).startswith("sha256:")
    assert report["scenarios"]["semantic_replay_rejected"] is True


def test_benchmark_wrapper_is_bounded_and_repeatable() -> None:
    report = run_benchmark(_SMOKE_ITERATIONS)
    assert report["iterations"] == _SMOKE_ITERATIONS
    assert report["min_ns"] <= report["median_ns"] <= report["max_ns"]
    assert report["p95_ns"] <= report["max_ns"]

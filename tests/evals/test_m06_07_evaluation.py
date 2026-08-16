"""Evaluator and benchmark checks for M06-07."""

from __future__ import annotations

from evals.m06_07.benchmark import benchmark
from evals.m06_07.run import evaluate

BENCHMARK_ITERATIONS = 2


def test_m0607_evaluator_covers_calibration_abstention_and_replay() -> None:
    report = evaluate()
    assert report.calibrated_status == "calibrated"
    assert report.upstream_abstained_status == "abstained"
    assert report.coverage_abstained_status == "abstained"
    assert report.selected_estimate is True
    assert report.prediction_set_present is True
    assert report.replay_verified is True
    assert report.deterministic is True
    assert report.passed is True


def test_m0607_benchmark_is_deterministic_and_within_provisional_budget() -> None:
    report = benchmark(iterations=BENCHMARK_ITERATIONS)
    assert report.iterations == BENCHMARK_ITERATIONS
    assert report.stratum_count == 1
    assert report.estimate_count == 1
    assert report.mean_ns > 0
    assert report.p95_ns > 0
    assert report.passed is True

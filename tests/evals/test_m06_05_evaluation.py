"""Evaluator and benchmark checks for M06-05."""

from __future__ import annotations

from evals.m06_05.benchmark import benchmark
from evals.m06_05.run import evaluate

BENCHMARK_ITERATIONS = 2
CONSTRAINT_COUNT = 2


def test_m0605_evaluator_covers_integration_abstention_ablation_and_replay() -> None:
    report = evaluate()
    assert report.integrated_status == "integrated"
    assert report.abstained_status == "abstained"
    assert report.unsupported_status == "abstained"
    assert report.replay_verified is True
    assert report.ablation_present is True
    assert report.hard_violation_reported is True
    assert report.deterministic is True
    assert report.passed is True


def test_m0605_benchmark_is_deterministic_and_within_provisional_budget() -> None:
    report = benchmark(iterations=BENCHMARK_ITERATIONS)
    assert report.iterations == BENCHMARK_ITERATIONS
    assert report.feature_count == 1
    assert report.constraint_count == CONSTRAINT_COUNT
    assert report.mean_ns > 0
    assert report.p95_ns > 0
    assert report.passed is True

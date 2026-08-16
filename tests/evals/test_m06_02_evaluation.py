"""Evaluator and benchmark checks for M06-02."""

from __future__ import annotations

from evals.m06_02.benchmark import benchmark
from evals.m06_02.run import evaluate

BENCHMARK_ITERATIONS = 2


def test_m0602_evaluator_covers_construct_abstention_and_replay() -> None:
    report = evaluate()

    assert report.constructed_status == "constructed"
    assert report.abstained_status == "abstained"
    assert report.replay_verified is True
    assert report.explicit_mask is True
    assert report.deterministic is True
    assert report.passed is True


def test_m0602_benchmark_is_deterministic_and_within_provisional_budget() -> None:
    report = benchmark(iterations=BENCHMARK_ITERATIONS)

    assert report.iterations == BENCHMARK_ITERATIONS
    assert report.feature_count == 1
    assert report.mean_ns > 0
    assert report.p95_ns > 0
    assert report.passed is True

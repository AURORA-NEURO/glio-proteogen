"""Focused evaluator and benchmark checks for the provisional M05-08 release."""

from __future__ import annotations

from evals.m05_08.benchmark import benchmark
from evals.m05_08.run import evaluate

BENCHMARK_ITERATIONS = 2
PACKAGE_MEMBER_COUNT = 4


def test_m0508_evaluator_covers_quarantine_release_and_replay() -> None:
    report = evaluate()

    assert report.authorized_without_verifier == "quarantined"
    assert report.authorized_with_verifier == "released"
    assert report.safe_failure is True
    assert report.tamper_verified is True
    assert report.passed is True


def test_m0508_benchmark_is_deterministic_and_within_provisional_budget() -> None:
    report = benchmark(iterations=BENCHMARK_ITERATIONS)

    assert report.iterations == BENCHMARK_ITERATIONS
    assert report.package_member_count == PACKAGE_MEMBER_COUNT
    assert report.mean_ns > 0
    assert report.p95_ns > 0
    assert report.passed is True

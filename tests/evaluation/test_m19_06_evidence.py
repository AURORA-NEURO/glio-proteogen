"""Evidence gates for M19-06 evaluator and benchmark reports."""

from __future__ import annotations

from evals.m19_06.benchmark import run_benchmark
from evals.m19_06.run import run

MIN_ADVERSARIAL_CASES = 7


def test_m19_06_evaluator_meets_authority_and_adversarial_target() -> None:
    report = run()
    assert report["status"] == "PASS"
    coverage = report["coverage_percent"]
    target = report["target_coverage_percent"]
    adversarial = report["adversarial_case_count"]
    assert isinstance(coverage, (int, float))
    assert isinstance(target, (int, float))
    assert isinstance(adversarial, int)
    assert coverage >= target
    assert adversarial >= MIN_ADVERSARIAL_CASES


def test_m19_06_benchmark_is_deterministic_and_within_budget() -> None:
    report = run_benchmark()
    assert report.passed is True
    assert report.request_digest.startswith("sha256:")
    assert report.result_digest.startswith("sha256:")

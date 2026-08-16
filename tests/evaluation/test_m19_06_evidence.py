"""Evidence gates for M19-06 evaluator and benchmark reports."""

from __future__ import annotations

from evals.m19_06.benchmark import run_benchmark
from evals.m19_06.run import run

MIN_ADVERSARIAL_CASES = 7


def test_m19_06_evaluator_meets_authority_and_adversarial_target() -> None:
    report = run()
    assert report["status"] == "PASS"
    assert report["coverage_percent"] >= report["target_coverage_percent"]
    assert report["adversarial_case_count"] >= MIN_ADVERSARIAL_CASES


def test_m19_06_benchmark_is_deterministic_and_within_budget() -> None:
    report = run_benchmark()
    assert report.passed is True
    assert report.request_digest.startswith("sha256:")
    assert report.result_digest.startswith("sha256:")

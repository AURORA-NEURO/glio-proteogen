"""Locked M10-03 evaluator checks."""
# ruff: noqa: PLR2004

from evals.m10_03.benchmark import run_benchmark
from evals.m10_03.run import evaluate, main


def test_evaluator_matrix_passes() -> None:
    report = evaluate()
    assert all(report["cases"].values())


def test_evaluator_is_deterministic() -> None:
    assert evaluate() == evaluate()


def test_evaluator_main_returns_success() -> None:
    assert main() == 0


def test_evaluator_is_fixture_bound() -> None:
    report = evaluate()
    assert report["declared_cases"] == 11
    assert report["declared_case_ids"] == report["executed_case_ids"]
    assert report["fixture_digest"].startswith("sha256:")
    assert report["passed"] is True


def test_benchmark_is_deterministic_and_within_provisional_budget() -> None:
    report = run_benchmark(iterations=3)
    assert report.deterministic is True
    assert report.passed is True
    assert report.target_count == 3

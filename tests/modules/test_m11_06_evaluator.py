"""Evaluator and benchmark evidence for M11-06."""

import pytest


from evals.m11_06.benchmark import (
    M1106InvalidIterationsError,
    run_benchmark,
)
from evals.m11_06.run import fixture_cases, run_evaluator


def test_evaluator_fixture_is_complete_and_passes() -> None:
    report = run_evaluator()
    assert report["module_id"] == "GLIO-PROTEOGEN-M11-06"
    assert report["passed"] is True
    assert report["declared"] == len(fixture_cases())
    assert report["executed"] == report["declared"]
    assert report["fixture_digest"] == (
        "sha256:63b91844d2890d0aa9916b7f46a053f6bb7b3bf93887f81e117b3572d02eec30"
    )


def test_benchmark_is_inside_provisional_budgets() -> None:
    report = run_benchmark(5)
    assert report["passed"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]


def test_benchmark_rejects_non_positive_iterations() -> None:
    with pytest.raises(M1106InvalidIterationsError):
        run_benchmark(0)

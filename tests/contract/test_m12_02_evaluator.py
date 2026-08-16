"""Evaluator and benchmark checks for M12-02."""

from typing import Any, cast

from evals.m12_02.benchmark import run_benchmark
from evals.m12_02.run import fixture_cases, run_evaluator

_CASE_COUNT = 6
_BENCHMARK_ITERATIONS = 3


def test_fixture_evaluator_covers_support_conflict_and_authorization() -> None:
    report = cast("dict[str, Any]", run_evaluator())
    assert report["module_id"] == "GLIO-PROTEOGEN-M12-02"
    assert report["passed"] is True
    assert report["declared"] == _CASE_COUNT
    assert report["executed"] == _CASE_COUNT
    assert report["failed"] == []
    outcomes = cast("list[dict[str, Any]]", report["outcomes"])
    assert {item["case_id"] for item in outcomes} == {item["case_id"] for item in fixture_cases()}
    assert str(report["fixture_digest"]).startswith("sha256:")


def test_benchmark_respects_declared_provisional_budgets() -> None:
    report = cast("dict[str, Any]", run_benchmark(_BENCHMARK_ITERATIONS))
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]
    assert report["within_budget"] is True

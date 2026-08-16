"""Evaluator and benchmark acceptance tests for M13-02."""

from evals.m13_02.benchmark import run_benchmark
from evals.m13_02.run import run_evaluator

_CASE_COUNT = 7
_BENCHMARK_ITERATIONS = 3


def test_m13_02_fixture_matrix_is_complete_and_green() -> None:
    report = run_evaluator()
    assert report["module_id"] == "GLIO-PROTEOGEN-M13-02"
    assert report["declared_cases"] == _CASE_COUNT
    assert report["executed_cases"] == _CASE_COUNT
    assert report["passed_cases"] == _CASE_COUNT
    assert report["all_passed"] is True
    assert (
        report["fixture_digest"]
        == "sha256:632ae56d0c883a7ea81024448e407b29d55abf574d969d8d4addd561e69fb911"
    )


def test_m13_02_benchmark_respects_provisional_budgets() -> None:
    report = run_benchmark(_BENCHMARK_ITERATIONS)
    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["passed"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]

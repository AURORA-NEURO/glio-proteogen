"""Release evaluator and benchmark checks for M07-04."""

from __future__ import annotations

from evals.m07_04.benchmark import run_benchmark
from evals.m07_04.run import evaluate, request

from glio_proteogen.modules.c07_copy_number_dosage.m07_04_probabilistic_advanced_estimator import (
    M0704Service,
)

_MINIMUM_CHECK_COUNT = 10


def test_evaluator_passes_all_checks() -> None:
    report = evaluate()
    assert report["passed"] is True
    assert report["check_count"] >= _MINIMUM_CHECK_COUNT


def test_benchmark_passes_provisional_budget() -> None:
    report = run_benchmark(iterations=3)
    assert report["passed"] is True
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]


def test_service_result_is_deterministic_across_instances() -> None:
    request_value = request()
    first = M0704Service().execute(request_value)
    second = M0704Service().execute(request_value)
    assert first == second
    assert first.result_digest == second.result_digest

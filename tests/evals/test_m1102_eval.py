"""Evaluator and benchmark gates for M11-02."""

from evals.m11_02.benchmark import measure
from evals.m11_02.run import run

_EXPECTED_CHECK_COUNT = 8


def test_m1102_evaluator_matrix_passes() -> None:
    evidence = run()
    assert evidence["module_id"] == "GLIO-PROTEOGEN-M11-02"
    assert evidence["passed"] is True
    assert evidence["check_count"] == _EXPECTED_CHECK_COUNT
    assert all(item["passed"] for item in evidence["checks"])


def test_m1102_benchmark_respects_provisional_budget() -> None:
    receipt = measure(3)
    assert receipt["passed"] is True
    assert receipt["mean_ns"] < receipt["budget_mean_ns"]
    assert receipt["p95_ns"] < receipt["budget_p95_ns"]

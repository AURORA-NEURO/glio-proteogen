"""Evaluator and benchmark gates for provisional M10-07."""

from evals.m10_07.benchmark import run_benchmark
from evals.m10_07.run import run_evaluation

_CHECK_COUNT = 10
_ITERATIONS = 10


def test_m10_07_evaluator_matrix_passes() -> None:
    report = run_evaluation()
    assert report["passed"] is True
    assert (
        report["authority_sha256"]
        == "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert report["authority_lines"] == [3540, 3583]
    assert len(report["checks"]) == _CHECK_COUNT


def test_m10_07_benchmark_meets_provisional_budgets() -> None:
    report = run_benchmark()
    assert report.passed is True
    assert report.iterations == _ITERATIONS
    assert report.p95_ns <= report.p95_budget_ns

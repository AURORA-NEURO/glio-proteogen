"""Executable evaluator and benchmark checks for M27-02."""

from evals.m27_02.benchmark import run_benchmark
from evals.m27_02.run import run_evaluation

_SCENARIO_COUNT = 2
_ADVERSARIAL_COUNT = 4
_BENCHMARK_ITERATIONS = 3


def test_m2702_evaluator_matrix_passes() -> None:
    report = run_evaluation()

    assert report["passed"] is True
    assert report["scenario_count"] == _SCENARIO_COUNT
    assert report["adversarial_count"] == _ADVERSARIAL_COUNT
    assert all(report["adversarial"].values())


def test_m2702_locked_benchmark_is_within_budgets() -> None:
    report = run_benchmark(iterations=_BENCHMARK_ITERATIONS)

    assert report["passed"] is True
    assert report["iterations"] == _BENCHMARK_ITERATIONS

"""M07-06 evaluator and benchmark tests."""

from evals.m07_06.benchmark import run_benchmark
from evals.m07_06.run import run_evaluation

_SCENARIO_COUNT = 5


def test_m07_06_evaluator_passes_all_scenarios() -> None:
    report = run_evaluation()
    assert report["passed"] is True
    assert report["scenario_count"] == _SCENARIO_COUNT


def test_m07_06_benchmark_is_within_provisional_budget() -> None:
    report = run_benchmark(iterations=3)
    assert report["passed"] is True

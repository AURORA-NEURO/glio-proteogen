"""Executable M25-08 evaluator and benchmark tests."""

from evals.m25_08.benchmark import run_benchmark
from evals.m25_08.evaluator import evaluate, run_adversarial, run_scenarios

_SCENARIOS = 9
_HOSTILE = 4
_ITERATIONS = 3


def test_locked_scenarios_and_adversarial_matrix_pass() -> None:
    scenarios = run_scenarios()
    hostile = run_adversarial()
    assert len(scenarios) == _SCENARIOS
    assert len(hostile) == _HOSTILE
    assert all(item.passed for item in (*scenarios, *hostile))
    assert evaluate() is True


def test_benchmark_respects_release_budgets() -> None:
    summary = run_benchmark(iterations=_ITERATIONS)
    assert summary.iterations == _ITERATIONS
    assert len(summary.samples_ns) == _ITERATIONS
    assert summary.passed

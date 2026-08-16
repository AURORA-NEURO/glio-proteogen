"""Evaluator and benchmark tests for M25-07."""

from evals.m25_07.benchmark import run_benchmark
from evals.m25_07.evaluator import evaluate, run_adversarial, run_scenarios

_LOCKED_SCENARIOS = 8
_ADVERSARIAL_SCENARIOS = 4
_BENCHMARK_ITERATIONS = 3


def test_m2507_locked_scenarios_pass() -> None:
    scenarios = run_scenarios()

    assert len(scenarios) == _LOCKED_SCENARIOS
    assert all(scenario.passed for scenario in scenarios)


def test_m2507_adversarial_scenarios_pass() -> None:
    scenarios = run_adversarial()

    assert len(scenarios) == _ADVERSARIAL_SCENARIOS
    assert all(scenario.passed for scenario in scenarios)
    assert evaluate() is True


def test_m2507_benchmark_is_within_provisional_budget() -> None:
    summary = run_benchmark(iterations=_BENCHMARK_ITERATIONS)

    assert summary.iterations == _BENCHMARK_ITERATIONS
    assert len(summary.samples_ns) == _BENCHMARK_ITERATIONS
    assert summary.passed is True

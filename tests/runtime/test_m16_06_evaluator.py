"""Evaluator corpus contract test."""

from evals.m16_06.run import main

_SCENARIO_COUNT = 8


def test_m1606_locked_evaluator_passes() -> None:
    report = main()
    assert report["declared"] == _SCENARIO_COUNT
    assert report["executed"] == _SCENARIO_COUNT
    assert report["passed"] is True

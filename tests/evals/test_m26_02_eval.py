"""Evaluator and benchmark evidence tests for M26-02."""

from evals.m26_02.evaluate import evaluate

_SCENARIO_COUNT = 7


def test_frozen_m26_02_scenario_matrix_passes() -> None:
    report = evaluate()
    assert report["scenarioCount"] == _SCENARIO_COUNT
    assert report["passed"] == report["scenarioCount"]
    assert report["fixtureDigest"].startswith("sha256:")
    assert report["scenarios"]["supported"]["status"] == "built"

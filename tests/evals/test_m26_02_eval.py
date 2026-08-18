"""Evaluator and benchmark evidence tests for M26-02."""

from evals.m26_02.evaluate import evaluate

_SCENARIO_COUNT = 8


def test_frozen_m26_02_scenario_matrix_passes() -> None:
    report = evaluate()
    assert report["scenarioCount"] == _SCENARIO_COUNT
    assert report["passed"] == report["scenarioCount"]
    assert report["fixtureDigest"].startswith("sha256:")
    assert report["scenarios"]["supported"]["status"] == "built"
    assert report["scenarios"]["semantic_tamper_replay"]["tamper"] == (
        "self-rehashed semantic mutation rejected"
    )

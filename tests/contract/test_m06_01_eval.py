"""Locked M06-01 evaluator checks."""

import json

import pytest
from evals.m06_01.run import SCENARIO_PATH, main

_SCENARIO_COUNT = 6


def test_m06_01_evaluator_replays_matrix(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["module_id"] == "GLIO-PROTEOGEN-M06-01"
    assert report["passed"] is True
    assert report["scenario_count"] == _SCENARIO_COUNT
    assert all(check["passed"] for check in report["checks"])


def test_m06_01_fixture_is_synthetic_and_closed() -> None:
    corpus = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))

    assert corpus["data_classification"] == "synthetic_nonclinical"
    assert corpus["claims_ceiling"] == "formal-state-validation-not-biomarker-inference"
    assert len(corpus["scenarios"]) == _SCENARIO_COUNT

"""Locked synthetic evaluator checks for M05-07."""

import json

import pytest
from evals.m05_07.run import SCENARIO_PATH, main

_SCENARIO_COUNT = 7
_DIMENSION_COUNT = 8


def test_m05_07_evaluator_replays_locked_matrix(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["module_id"] == "GLIO-PROTEOGEN-M05-07"
    assert report["passed"] is True
    assert report["scenario_count"] == _SCENARIO_COUNT
    assert all(check["passed"] for check in report["checks"])


def test_m05_07_fixture_is_present_and_closed() -> None:
    corpus = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))

    assert corpus["module_id"] == "GLIO-PROTEOGEN-M05-07"
    assert len(corpus["dimensions"]) == _DIMENSION_COUNT
    assert len(corpus["scenarios"]) == _SCENARIO_COUNT

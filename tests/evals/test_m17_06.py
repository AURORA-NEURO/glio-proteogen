"""Evaluator matrix tests for provisional M17-06."""

from evals.m17_06.run import EXPECTED_CASE_IDS, evaluate


def test_locked_m1706_evaluator_passes_every_case() -> None:
    report = evaluate()
    assert report["passed"] is True
    assert report["declared_cases"] == len(EXPECTED_CASE_IDS)
    assert report["executed_cases"] == len(EXPECTED_CASE_IDS)
    assert report["passed_cases"] == len(EXPECTED_CASE_IDS)

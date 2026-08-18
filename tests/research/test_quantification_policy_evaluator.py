"""Evaluator gate for research-only quantification controls."""

from __future__ import annotations

from evals.research_proteomics.quantification_policy import run_quantification_policy_evaluator


def test_quantification_policy_evaluator_is_green() -> None:
    report = run_quantification_policy_evaluator()
    assert report["passed"] is True
    assert report["declared"] == report["executed"] == 2

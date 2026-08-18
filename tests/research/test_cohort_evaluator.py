"""Evaluator-level locks for the research cohort matrix."""

from __future__ import annotations

from typing import cast

from evals.research_proteomics.cohort import run_evaluator


def test_locked_cohort_evaluator() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared"] == 4
    assert report["executed"] == 4
    outcomes = cast("list[dict[str, object]]", report["outcomes"])
    assert all(item["passed"] is True for item in outcomes)

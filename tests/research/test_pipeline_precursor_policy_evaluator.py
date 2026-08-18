"""Evaluator coverage for precursor tolerance threshold and replay binding."""

from __future__ import annotations

from typing import cast

from evals.research_proteomics.precursor_policy import run_precursor_policy_evaluator


def test_precursor_policy_evaluator_is_complete() -> None:
    report = run_precursor_policy_evaluator()
    assert report["passed"] is True
    assert report["declared"] == report["executed"] == 8
    checks = cast("dict[str, bool]", report["checks"])
    assert all(checks.values())
    assert report["narrow_result_digest"] != report["broad_result_digest"]

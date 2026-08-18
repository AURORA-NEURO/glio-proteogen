"""Executable evaluator gate for the external evidence ledger."""

from __future__ import annotations

from evals.research_proteomics.evidence_aggregation import run_evidence_aggregation_evaluator


def test_external_evidence_evaluator_is_complete() -> None:
    report = run_evidence_aggregation_evaluator()
    assert report["passed"] is True
    assert report["declared"] == 6
    assert report["executed"] == 6
    outcomes = report["outcomes"]
    assert isinstance(outcomes, list)
    assert all(item["passed"] is True for item in outcomes)
    assert report["claim_boundary"] == (
        "caller-declared descriptive evidence only; no numerical fusion"
    )

"""PDC receipt media evaluator gate."""

from __future__ import annotations

from evals.research_proteomics.pdc_receipt import run_pdc_receipt_evaluator


def test_pdc_receipt_media_evaluator_is_green() -> None:
    report = run_pdc_receipt_evaluator()
    assert report["passed"] is True
    assert report["declared"] == report["executed"] == 5

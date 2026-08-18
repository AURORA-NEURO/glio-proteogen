"""Executable evaluator coverage for mzIdentML structural provenance."""

from __future__ import annotations

from typing import cast

from evals.research_proteomics.mzidentml_provenance import (
    run_mzidentml_provenance_evaluator,
)


def test_mzidentml_provenance_evaluator_is_complete() -> None:
    report = run_mzidentml_provenance_evaluator()
    assert report["passed"] is True
    assert report["declared"] == report["executed"] == 10
    assert all(cast("dict[str, bool]", report["checks"]).values())
    assert report["baseline_result_digest"] != report["bound_result_digest"]

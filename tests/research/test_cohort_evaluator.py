"""Evaluator-level locks for the research cohort matrix."""

from __future__ import annotations

from typing import cast

from evals.research_proteomics.cohort import run_evaluator


def test_locked_cohort_evaluator() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared"] == 6
    assert report["executed"] == 6
    outcomes = cast("list[dict[str, object]]", report["outcomes"])
    assert all(item["passed"] is True for item in outcomes)


def test_locked_cohort_evaluator_emits_replay_complete_projections() -> None:
    outcomes = cast("list[dict[str, object]]", run_evaluator()["outcomes"])
    for outcome in outcomes:
        projection = outcome["projection"]
        if outcome["id"] == "incompatible_search_space":
            assert projection is None
            continue
        assert isinstance(projection, dict)
        assert {
            "child_result_digests",
            "configuration",
            "group_accessions",
            "group_qc",
            "matrix",
            "result_digest",
            "sample_ids",
            "sample_qc",
            "raw_matrix",
            "normalized_matrix",
            "sample_scales",
            "label_qc",
            "label_group_evidence",
        } <= projection.keys()
        configuration = projection["configuration"]
        assert isinstance(configuration, dict)
        assert "sample_source_provenance" in configuration

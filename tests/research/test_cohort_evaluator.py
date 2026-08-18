"""Evaluator-level locks for the research cohort matrix."""

from __future__ import annotations

from typing import cast

from evals.research_proteomics.cohort import run_evaluator


def test_locked_cohort_evaluator() -> None:
    report = run_evaluator()
    assert report["passed"] is True
    assert report["declared"] == 10
    assert report["executed"] == 10
    outcomes = cast("list[dict[str, object]]", report["outcomes"])
    assert all(item["passed"] is True for item in outcomes)


def test_locked_cohort_evaluator_emits_replay_complete_projections() -> None:
    outcomes = cast("list[dict[str, object]]", run_evaluator()["outcomes"])
    for outcome in outcomes:
        projection = outcome["projection"]
        if outcome["id"] in {
            "incompatible_search_space",
            "duplicate_biological_source",
            "pdc_manifest_receipt_identity",
        }:
            assert projection is None
            continue
        assert isinstance(projection, dict)
        assert {
            "child_result_digests",
            "configuration",
            "evidence_bundle",
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
            "label_contrasts",
        } <= projection.keys()
        receipt = projection["evidence_bundle"]
        assert isinstance(receipt, dict)
        assert isinstance(receipt.get("digest"), str)
        records = receipt.get("records")
        assert isinstance(records, list)
        assert {item["evidence_id"] for item in records if isinstance(item, dict)} == {
            "cohort.matrix.v1",
            "cohort.provenance.v1",
            "cohort.qc.v1",
            "cohort.contrast.v1",
        }
        configuration = projection["configuration"]
        assert isinstance(configuration, dict)
        assert "sample_source_provenance" in configuration

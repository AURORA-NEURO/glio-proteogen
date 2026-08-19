"""Evaluator and adversarial coverage for research FDR/quantification/group semantics."""

from __future__ import annotations

from dataclasses import replace

import pytest
from evals.research_proteomics.fdr_quant_group_invariants import (
    run_fdr_quant_group_invariants_evaluator,
)

from glio_proteogen.research import Psm, infer_protein_group_candidates, target_decoy_qvalues


def test_fdr_quant_group_invariants_evaluator_is_green() -> None:
    report = run_fdr_quant_group_invariants_evaluator()
    assert report["passed"] is True
    assert report["declared"] == report["executed"] == 12


def test_fdr_rejects_inconsistent_accession_class_before_competition() -> None:
    forged = Psm("scan=1", "PEPTIDER", ("DECOY_P1",), 5.0, 3, decoy=False)
    with pytest.raises(ValueError, match="target/decoy flags"):
        target_decoy_qvalues((forged,))


def test_fdr_rejects_empty_accession_evidence() -> None:
    malformed = Psm("scan=1", "PEPTIDER", (), 5.0, 3, decoy=True)
    with pytest.raises(ValueError, match="at least one"):
        target_decoy_qvalues((malformed,))


def test_collision_class_must_match_mixed_accessions() -> None:
    malformed = Psm(
        "scan=1",
        "PEPTIDER",
        ("P1", "DECOY_P1"),
        5.0,
        3,
        decoy=False,
        target_decoy_collision=False,
    )
    with pytest.raises(ValueError, match="target/decoy flags"):
        target_decoy_qvalues((replace(malformed),))


def test_group_rejects_nonfinite_score_before_winner_selection() -> None:
    malformed = Psm("scan=1", "PEPTIDER", ("P1",), float("nan"), 3, decoy=False)
    with pytest.raises(ValueError, match="finite and non-negative"):
        infer_protein_group_candidates((malformed,), q_value_threshold=0.01)

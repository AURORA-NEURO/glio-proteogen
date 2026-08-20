"""Evaluator and adversarial coverage for research FDR/quantification/group semantics."""

from __future__ import annotations

from dataclasses import replace

import pytest
from evals.research_proteomics.fdr_quant_group_invariants import (
    run_fdr_quant_group_invariants_evaluator,
)

from glio_proteogen.research import (
    Psm,
    PsmCompetition,
    infer_protein_group_candidates,
    target_decoy_qvalues,
)


def test_fdr_quant_group_invariants_evaluator_is_green() -> None:
    report = run_fdr_quant_group_invariants_evaluator()
    assert report["passed"] is True
    assert report["declared"] == report["executed"] == 13


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


def test_fdr_boundaries_reject_zero_fragment_evidence() -> None:
    zero_ion = Psm("scan=zero", "PEPTIDER", ("P1",), 5.0, 0, decoy=False)
    with pytest.raises(ValueError, match="matched_ions must be a positive integer"):
        target_decoy_qvalues((zero_ion,))
    with pytest.raises(ValueError, match="matched_ions must be a positive integer"):
        infer_protein_group_candidates((zero_ion,), q_value_threshold=0.01)


@pytest.mark.parametrize(
    ("accessions", "message"),
    [
        ((" DECOY_P1",), "bounded opaque"),
        (("P1", "P1"), "must be unique"),
    ],
)
def test_fdr_boundaries_reject_ambiguous_accession_identity(
    accessions: tuple[str, ...], message: str
) -> None:
    malformed = Psm("scan=identity", "PEPTIDER", accessions, 5.0, 3, decoy=False)
    with pytest.raises(ValueError, match=message):
        target_decoy_qvalues((malformed,))
    with pytest.raises(ValueError, match=message):
        infer_protein_group_candidates((malformed,), q_value_threshold=0.01)


def test_duplicate_spectrum_contenders_are_permutation_stable() -> None:
    lower_signal = Psm(
        "scan=duplicate",
        "PEPTIDER",
        ("P1",),
        5.0,
        3,
        decoy=False,
        matched_intensity=2.0,
    )
    higher_signal = replace(lower_signal, matched_intensity=20.0)

    forward = target_decoy_qvalues((lower_signal, higher_signal))
    reverse = target_decoy_qvalues((higher_signal, lower_signal))
    assert forward == reverse
    assert forward[0].matched_intensity == 20.0

    forward_receipt = PsmCompetition.from_candidates((lower_signal, higher_signal))
    reverse_receipt = PsmCompetition.from_candidates((higher_signal, lower_signal))
    assert forward_receipt == reverse_receipt

    _, forward_summary = infer_protein_group_candidates(
        (lower_signal, higher_signal), q_value_threshold=0.01
    )
    _, reverse_summary = infer_protein_group_candidates(
        (higher_signal, lower_signal), q_value_threshold=0.01
    )
    assert forward_summary.competition_digest == reverse_summary.competition_digest


def test_group_abstains_when_only_some_accessions_have_unique_peptide_support() -> None:
    candidates, summary = infer_protein_group_candidates(
        (
            Psm("shared", "SHARED", ("P1", "P2"), 10.0, 3, decoy=False),
            Psm("unique", "UNIQUE", ("P1",), 9.0, 3, decoy=False),
            Psm("decoy", "DECOY_ONLY", ("DECOY_P3",), 1.0, 3, decoy=True),
        ),
        q_value_threshold=0.01,
    )

    target = next(item for item in candidates if item.accessions == ("P1", "P2"))
    assert target.q_value == 0.0
    assert target.identifiability == "partially_unique_ambiguous"
    assert target.acceptance == "abstained"
    assert summary.accepted_targets == 0

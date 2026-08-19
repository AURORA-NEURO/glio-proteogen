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


@pytest.mark.parametrize("decoy_prefix", ["", "bad prefix", "\t", "x" * 33])
def test_fdr_rejects_invalid_decoy_prefix_before_classification(decoy_prefix: str) -> None:
    target = Psm("scan=1", "PEPTIDER", ("P1",), 5.0, 3, decoy=False)
    with pytest.raises(ValueError, match="decoy_prefix"):
        target_decoy_qvalues((target,), decoy_prefix=decoy_prefix)


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


def test_group_fdr_rejects_malformed_target_before_decoy_calibration() -> None:
    malformed_target = Psm("scan=target", "PEPTIDER", ("P1 ",), 5.0, 3, decoy=False)
    valid_decoy = Psm(
        "scan=decoy", "DECOY_PEPTIDER", ("DECOY_P1",), 3.0, 3, decoy=True
    )
    with pytest.raises(ValueError, match="accessions"):
        infer_protein_group_candidates(
            (malformed_target, valid_decoy), q_value_threshold=0.01
        )


@pytest.mark.parametrize(
    ("psm", "message"),
    [
        (Psm("scan=1", "PEPTIDER", ("P1",), 5.0, 0, decoy=False), "matched_ions"),
        (
            Psm(
                "scan=1",
                "PEPTIDER",
                ("P1",),
                5.0,
                3,
                decoy=False,
                matched_intensity=float("nan"),
            ),
            "matched_intensity",
        ),
        (
            Psm(
                "scan=1",
                "PEPTIDER",
                ("P1",),
                5.0,
                3,
                decoy=False,
                mean_fragment_error_da=float("inf"),
            ),
            "mean_fragment_error_da",
        ),
        (
            Psm(
                "scan=1",
                "PEPTIDER",
                ("P1",),
                5.0,
                3,
                decoy=False,
                precursor_error_ppm=-1.0,
            ),
            "precursor_error_ppm",
        ),
        (
            Psm("scan=1", "PEPTIDER", ("P1",), 5.0, 3, decoy=False, q_value=1.1),
            "q_value",
        ),
    ],
)
def test_fdr_rejects_nonfinite_or_out_of_range_psm_measurements(psm: Psm, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        target_decoy_qvalues((psm,))


def test_fdr_rejects_unbounded_or_non_opaque_psm_identifiers() -> None:
    with pytest.raises(ValueError, match="spectrum_id"):
        target_decoy_qvalues((Psm("scan 1", "PEPTIDER", ("P1",), 5.0, 3, decoy=False),))
    with pytest.raises(ValueError, match="accessions"):
        target_decoy_qvalues((Psm("scan=1", "PEPTIDER", ("P1", "P1"), 5.0, 3, decoy=False),))


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

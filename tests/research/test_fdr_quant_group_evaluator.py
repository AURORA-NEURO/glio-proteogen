"""Evaluator and adversarial coverage for research FDR/quantification/group semantics."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256

import pytest
from evals.research_proteomics.fdr_quant_group_invariants import (
    run_fdr_quant_group_invariants_evaluator,
)

from glio_proteogen.research import (
    ProteinGroupCandidate,
    ProteinGroupFdrSummary,
    Psm,
    PsmCompetition,
    infer_protein_group_candidates,
    infer_protein_groups,
    target_decoy_qvalues,
    verify_protein_group_fdr_summary,
)


def test_fdr_quant_group_invariants_evaluator_is_green() -> None:
    report = run_fdr_quant_group_invariants_evaluator()
    assert report["passed"] is True
    assert report["declared"] == report["executed"] == 15


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
    valid_decoy = Psm("scan=decoy", "DECOY_PEPTIDER", ("DECOY_P1",), 3.0, 3, decoy=True)
    with pytest.raises(ValueError, match="accessions"):
        infer_protein_group_candidates((malformed_target, valid_decoy), q_value_threshold=0.01)


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


def test_competition_receipt_validates_class_and_binds_winner_for_custom_prefix() -> None:
    target = Psm("scan=custom", "PEPTIDER", ("P1",), 5.0, 3, decoy=False)
    forged = replace(target, protein_accessions=("DECOY_P1",))
    with pytest.raises(ValueError, match="target/decoy flags"):
        PsmCompetition.from_candidates((forged,))

    decoy = Psm(
        "scan=custom",
        "PEPTIDER",
        ("REV_P1",),
        6.0,
        3,
        decoy=True,
    )
    receipt = PsmCompetition.from_candidates((target, decoy), decoy_prefix="REV_")
    assert receipt.decoy_prefix == "REV_"
    assert receipt.winner_decoy is True
    assert receipt.winner_collision is False
    assert receipt.as_dict()["winner_decoy"] is True


def test_competition_receipt_rejects_nonfinite_candidate_score() -> None:
    malformed = Psm("scan=nonfinite", "PEPTIDER", ("P1",), float("inf"), 3, decoy=False)
    with pytest.raises(ValueError, match="score"):
        PsmCompetition.from_candidates((malformed,))


def test_group_fdr_abstains_partial_unique_support_in_connected_component() -> None:
    candidates, summary = infer_protein_group_candidates(
        (
            Psm("shared", "SHARED", ("P1", "P2"), 5.0, 3, decoy=False),
            Psm("unique", "UNIQUE_P2", ("P2",), 4.0, 3, decoy=False),
            Psm("decoy", "DECOY_P", ("DECOY_P",), 1.0, 3, decoy=True),
        ),
        q_value_threshold=0.01,
    )
    target = next(item for item in candidates if item.status == "target")
    assert target.accessions == ("P1", "P2")
    assert target.unique_supported_accessions == ("P2",)
    assert target.ambiguous_accessions == ("P1",)
    assert target.identifiability == "partially_unique_ambiguous"
    assert target.acceptance == "abstained"
    assert summary.partially_unique_candidates == 1
    assert target.as_dict()["ambiguous_accessions"] == ["P1"]


def test_group_fdr_receipt_binds_partition_and_declares_empirical_error_evidence() -> None:
    target = Psm("target", "PEPTIDER", ("P1",), 5.0, 3, decoy=False)
    decoy = Psm("decoy", "PEPTIDEK", ("DECOY_P1",), 4.0, 3, decoy=True)
    candidates, summary = infer_protein_group_candidates((target, decoy), q_value_threshold=0.01)

    assert summary.evidence_status == "empirical_target_decoy_evidence"
    assert summary.error_candidates == 1
    assert summary.target_denominator == 1
    assert len(summary.group_partition_digest) == 64
    assert all(len(item.evidence_digest) == 64 for item in candidates)
    verify_protein_group_fdr_summary(candidates, summary)

    forged = replace(summary, group_partition_digest="0" * 64)
    with pytest.raises(ValueError, match="partition digest"):
        verify_protein_group_fdr_summary(candidates, forged)


def test_group_fdr_declares_missing_decoy_evidence_instead_of_zero_fdr() -> None:
    target = Psm("target", "PEPTIDER", ("P1",), 5.0, 3, decoy=False)
    candidates, summary = infer_protein_group_candidates((target,), q_value_threshold=0.01)

    assert summary.evidence_status == "abstained_no_decoy_evidence"
    assert summary.error_candidates == 0
    assert summary.target_denominator == 1
    assert candidates[0].q_value is None
    verify_protein_group_fdr_summary(candidates, summary)


@pytest.mark.parametrize(
    "mapping",
    [
        {"PEP": ["P1"]},
        {"PEP": ("P1", "P1")},
        {"PEP ": ("P1",)},
        {"PEP": ("P 1",)},
    ],
)
def test_protein_group_partition_rejects_malformed_memberships(
    mapping: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        infer_protein_groups(mapping)  # type: ignore[arg-type]


def _group_receipt() -> tuple[tuple[ProteinGroupCandidate, ...], ProteinGroupFdrSummary]:
    target = Psm("target", "PEPTIDER", ("P1",), 5.0, 3, decoy=False)
    decoy = Psm("decoy", "PEPTIDEK", ("DECOY_P1",), 4.0, 3, decoy=True)
    return infer_protein_group_candidates((target, decoy), q_value_threshold=0.01)


def test_group_receipt_rejects_invalid_partition_shapes_and_statuses() -> None:
    candidates, summary = _group_receipt()
    candidate = candidates[0]
    invalid_candidates = (
        replace(candidate, accessions=("Z", "A")),
        replace(candidate, unique_peptides=("PEPTIDEK",), shared_peptides=("PEPTIDEK",)),
        replace(candidate, status="unknown"),
        replace(candidate, acceptance="unknown"),
        replace(candidate, q_value=float("nan")),
        replace(candidate, evidence_digest="not-a-digest"),
    )
    for forged in invalid_candidates:
        with pytest.raises(ValueError):
            verify_protein_group_fdr_summary((forged,), summary)


def test_group_receipt_rejects_collision_and_shared_only_promotions() -> None:
    candidates, summary = _group_receipt()
    candidate = candidates[0]
    collision = replace(
        candidate,
        status="collision",
        q_value=0.01,
        acceptance="abstained",
    )
    with pytest.raises(ValueError, match="collision"):
        verify_protein_group_fdr_summary((collision,), summary)
    shared_only = replace(
        candidate,
        identifiability="shared_only_ambiguous",
        acceptance="accepted",
    )
    with pytest.raises(ValueError, match="shared-only"):
        verify_protein_group_fdr_summary((shared_only,), summary)


def test_group_receipt_rejects_order_duplicate_and_summary_count_tampering() -> None:
    candidates, summary = _group_receipt()
    target = Psm("target-2", "PEPTIDER2", ("P2",), 3.0, 3, decoy=False)
    expanded, expanded_summary = infer_protein_group_candidates(
        (
            *(
                Psm("target", "PEPTIDER", ("P1",), 5.0, 3, decoy=False),
                Psm("decoy", "PEPTIDEK", ("DECOY_P1",), 4.0, 3, decoy=True),
                target,
            ),
        ),
        q_value_threshold=0.01,
    )
    with pytest.raises(ValueError, match="sorted"):
        verify_protein_group_fdr_summary(expanded[::-1], expanded_summary)
    with pytest.raises(ValueError, match="unique"):
        verify_protein_group_fdr_summary((candidates[0], candidates[0]), summary)
    for field in ("candidates", "target_candidates", "decoy_candidates", "collision_candidates"):
        forged = replace(summary, **{field: getattr(summary, field) + 1})
        with pytest.raises(ValueError):
            verify_protein_group_fdr_summary(candidates, forged)
    forged = replace(summary, accepted_targets=summary.accepted_targets + 1)
    with pytest.raises(ValueError, match="accepted"):
        verify_protein_group_fdr_summary(candidates, forged)
    forged = replace(summary, error_candidates=summary.error_candidates + 1)
    with pytest.raises(ValueError, match="error"):
        verify_protein_group_fdr_summary(candidates, forged)
    forged = replace(summary, target_denominator=summary.target_denominator + 1)
    with pytest.raises(ValueError, match="denominator"):
        verify_protein_group_fdr_summary(candidates, forged)


def test_group_receipt_rejects_status_and_partition_digest_tampering() -> None:
    candidates, summary = _group_receipt()
    for status in (
        "abstained_no_group_candidates",
        "abstained_no_decoy_evidence",
        "abstained_no_target_denominator",
    ):
        forged = replace(summary, evidence_status=status)
        with pytest.raises(ValueError, match="status"):
            verify_protein_group_fdr_summary(candidates, forged)
    forged = replace(summary, group_partition_digest="0" * 64)
    with pytest.raises(ValueError, match="partition digest"):
        verify_protein_group_fdr_summary(candidates, forged)
    with pytest.raises(TypeError, match="summary"):
        verify_protein_group_fdr_summary(candidates, object())  # type: ignore[arg-type]


def test_group_receipt_rejects_partial_unique_promotion_and_incomplete_support() -> None:
    candidates, summary = infer_protein_group_candidates(
        (
            Psm("shared", "SHARED", ("P1", "P2"), 5.0, 3, decoy=False),
            Psm("unique", "UNIQUE_P2", ("P2",), 4.0, 3, decoy=False),
            Psm("decoy", "DECOY_P", ("DECOY_P",), 1.0, 3, decoy=True),
        ),
        q_value_threshold=0.01,
    )
    partial = next(item for item in candidates if item.status == "target")
    with pytest.raises(ValueError, match="partially unique"):
        verify_protein_group_fdr_summary(
            (
                replace(
                    partial,
                    acceptance="accepted",
                    q_value=0.0,
                ),
            ),
            replace(summary, candidates=1, target_candidates=1, error_candidates=0),
        )

    target_candidates, target_summary = _group_receipt()
    with pytest.raises(ValueError, match="incomplete"):
        verify_protein_group_fdr_summary(
            (replace(target_candidates[0], unique_supported_accessions=()),),
            replace(target_summary, group_partition_digest="0" * 64),
        )


def test_group_receipt_recomputes_q_values_and_summary_ambiguity_counts() -> None:
    candidates, summary = infer_protein_group_candidates(
        (
            Psm("decoy", "DECOY_P", ("DECOY_P",), 6.0, 3, decoy=True),
            Psm("target-1", "PEPTIDER", ("P1",), 5.0, 3, decoy=False),
            Psm("target-2", "PEPTIDEK", ("P2",), 4.0, 3, decoy=False),
        ),
        q_value_threshold=0.6,
    )
    target = next(item for item in candidates if item.accessions == ("P1",))
    forged_target = replace(target, q_value=0.0)
    forged_candidates = tuple(
        forged_target if item.accessions == target.accessions else item for item in candidates
    )
    forged_partition = sha256(
        json.dumps(
            [item.as_dict() for item in forged_candidates],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="q-values"):
        verify_protein_group_fdr_summary(
            forged_candidates,
            replace(summary, group_partition_digest=forged_partition),
        )

    with pytest.raises(ValueError, match="shared-peptide count"):
        verify_protein_group_fdr_summary(
            candidates,
            replace(summary, shared_peptide_candidates=summary.shared_peptide_candidates + 1),
        )
    with pytest.raises(ValueError, match="ratio"):
        verify_protein_group_fdr_summary(
            candidates,
            replace(summary, decoy_to_target_ratio=0.0),
        )


def test_group_receipt_rejects_invalid_competition_and_input_closure() -> None:
    candidates, summary = _group_receipt()
    invalid_summaries = (
        replace(summary, competition_digest="not-a-digest"),
        replace(summary, q_value_threshold=float("nan")),
        replace(summary, input_psms=summary.input_psms + 1),
        replace(summary, max_accepted_q_value=float("inf")),
    )
    for forged in invalid_summaries:
        with pytest.raises(ValueError):
            verify_protein_group_fdr_summary(candidates, forged)


def test_group_partition_rejects_non_mapping_and_group_decoy_prefix() -> None:
    with pytest.raises(TypeError, match="mapping"):
        infer_protein_groups(None)  # type: ignore[arg-type]
    target = Psm("target", "PEPTIDER", ("P1",), 1.0, 3, decoy=False)
    with pytest.raises(ValueError, match="decoy_prefix"):
        infer_protein_group_candidates((target,), q_value_threshold=0.01, decoy_prefix="bad prefix")

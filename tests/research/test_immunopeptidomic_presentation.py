"""Branch and replay tests for the caller-owned glioma presentation lane."""

from __future__ import annotations

import pytest

from glio_proteogen.research.immunopeptidomic_presentation import (
    HlaPresentationModel,
    PeptideObservation,
    analyze_immunopeptidomic_presentation,
    model_digest,
    presentation_profile,
    runtime,
    synthetic_presentation_request,
    verify_presentation_replay,
)


def test_synthetic_presentation_is_allele_aware_and_replay_closed() -> None:
    request = synthetic_presentation_request()
    result = analyze_immunopeptidomic_presentation(request)

    assert result.support == "supported"
    assert result.supported_peptide_count == 5
    assert result.supported_allele_count == 2
    for item in result.candidates:
        if item.support == "supported":
            assert item.interval_low is not None
            assert item.interval_high is not None
            assert item.presentation_probability is not None
            assert item.interval_low <= item.presentation_probability <= item.interval_high
            assert item.ablations
    assert verify_presentation_replay(request, result)


def test_request_order_is_canonicalized() -> None:
    request = synthetic_presentation_request()
    reordered = request.model_copy(
        update={
            "hla_alleles": tuple(reversed(request.hla_alleles)),
            "peptides": tuple(reversed(request.peptides)),
            "models": tuple(reversed(request.models)),
            "source_digests": tuple(reversed(request.source_digests)),
        }
    )
    assert request.request_digest == reordered.request_digest
    assert analyze_immunopeptidomic_presentation(request) == (
        analyze_immunopeptidomic_presentation(reordered)
    )


def test_missing_and_unsupported_evidence_never_becomes_negative_observation() -> None:
    request = synthetic_presentation_request().model_copy(
        update={
            "peptides": (
                *synthetic_presentation_request().peptides[:2],
                PeptideObservation(
                    peptide_id="missing", sequence="SLYNTVATL", source_gene="EGFR", state="missing"
                ),
                PeptideObservation(
                    peptide_id="unsupported",
                    sequence="SLYNTVATL",
                    source_gene="EGFR",
                    state="unsupported",
                ),
            )
        }
    )
    result = analyze_immunopeptidomic_presentation(request)
    assert result.support == "abstained"
    assert [item.support for item in result.candidates].count("unsupported") == 2
    assert all(
        item.presentation_probability is None
        for item in result.candidates
        if item.support == "unsupported"
    )


def test_left_censored_expression_is_one_sided() -> None:
    request = synthetic_presentation_request().model_copy(
        update={
            "peptides": tuple(
                item.model_copy(
                    update={
                        "state": "left_censored",
                        "expression_effect": None,
                        "detection_limit": -1.0,
                    }
                )
                if item.peptide_id == "pep-1"
                else item
                for item in synthetic_presentation_request().peptides
            )
        }
    )
    result = analyze_immunopeptidomic_presentation(request)
    row = next(item for item in result.candidates if item.peptide_id == "pep-1")
    assert row.support == "supported"
    assert row.expression_contribution == -1.0


def test_unsupported_allele_is_limited_and_short_support_abstains() -> None:
    request = synthetic_presentation_request().model_copy(
        update={
            "hla_alleles": ("HLA-A*02:01", "HLA-C*03:04"),
            "models": (synthetic_presentation_request().models[0],),
        }
    )
    result = analyze_immunopeptidomic_presentation(request)
    assert result.support == "limited"
    assert result.supported_allele_count == 1

    short = request.model_copy(update={"peptides": request.peptides[:2]})
    short_result = analyze_immunopeptidomic_presentation(short)
    assert short_result.support == "abstained"
    assert short_result.abstention_reason is not None


def test_zero_bootstrap_is_replay_stable() -> None:
    request = synthetic_presentation_request().model_copy(update={"bootstrap_replicates": 0})
    result = analyze_immunopeptidomic_presentation(request)
    assert all(
        item.interval_low == item.interval_high
        for item in result.candidates
        if item.support == "supported"
    )
    assert verify_presentation_replay(request, result)


def test_forged_model_digest_and_malformed_allele_are_rejected() -> None:
    request = synthetic_presentation_request()
    forged = request.models[0].model_copy(update={"model_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValueError, match="model digest"):
        HlaPresentationModel.model_validate(forged.model_dump(mode="python"), strict=True)
    with pytest.raises(ValueError, match="canonical HLA"):
        type(request).model_validate(
            request.model_copy(update={"hla_alleles": ("HLA-A0201",)}).model_dump(mode="python"),
            strict=True,
        )


def test_profile_digest_is_bound_and_model_digest_is_deterministic() -> None:
    request = synthetic_presentation_request()
    assert presentation_profile().profile_digest == presentation_profile().profile_digest
    assert model_digest(request.models[0]) == request.models[0].model_digest


def test_pssm_uses_position_log_odds_sum_and_noisy_or_is_monotone() -> None:
    request = synthetic_presentation_request()
    peptide = request.peptides[0]
    score = runtime._score_allele(request.models[0], peptide)
    assert score is not None
    assert score.binding_score == 4.0
    one_allele = runtime._aggregate_probabilities((0.0,))
    two_alleles = runtime._aggregate_probabilities((0.0, 0.0))
    stronger_allele = runtime._aggregate_probabilities((0.0, 1.0))
    assert one_allele == pytest.approx(0.5)
    assert two_alleles == pytest.approx(0.75)
    assert stronger_allele > two_alleles


def test_replay_rejects_modified_result() -> None:
    request = synthetic_presentation_request()
    result = analyze_immunopeptidomic_presentation(request)
    changed = result.model_copy(update={"sample_id": "other-sample"})
    with pytest.raises(ValueError, match="replay"):
        verify_presentation_replay(request, changed)

"""Determinism and adversarial evidence-state tests for Neftel programs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.research.neftel_protein_programs import (
    ExactProgramId,
    ProteinEvidenceState,
    ProteinProgramObservation,
    ProteinProgramRequest,
    ReplayVerificationRequest,
    analyze_neftel_protein_programs,
    verify_neftel_protein_program_replay,
)
from glio_proteogen.research.neftel_protein_programs.canonical import (
    computational_request_digest,
    sha256_digest,
)
from glio_proteogen.research.neftel_protein_programs.catalog import marker_catalog
from glio_proteogen.research.neftel_protein_programs.profile import algorithm_profile

SOURCE_A = sha256_digest("neftel-property-source-a")
SOURCE_B = sha256_digest("neftel-property-source-b")


def _background_symbols(count: int) -> tuple[str, ...]:
    catalog = marker_catalog()
    program_symbols = {
        marker.normalized_symbol
        for markers in catalog.programs.values()
        for marker in markers
        if marker.protein_eligible
    }
    return tuple(sorted(catalog.protein_background_symbols - program_symbols)[:count])


def _active(
    symbol: str,
    effect: float,
    index: int,
    *,
    state: ProteinEvidenceState = ProteinEvidenceState.OBSERVED,
    provenance: str = SOURCE_A,
) -> ProteinProgramObservation:
    return ProteinProgramObservation(
        observation_id=f"obs.{index}",
        gene_symbol=symbol,
        state=state,
        standardized_effect=effect,
        standard_error=0.3,
        quality_weight=1.0,
        provenance_digest=provenance,
    )


def _base_observations(*, provenance: str = SOURCE_A) -> tuple[ProteinProgramObservation, ...]:
    markers = tuple(
        marker.normalized_symbol
        for marker in marker_catalog().programs["AC"]
        if marker.protein_eligible
    )[:12]
    marker_observations = tuple(
        _active(symbol, 0.9 + index * 0.01, index, provenance=provenance)
        for index, symbol in enumerate(markers)
    )
    background = tuple(
        _active(symbol, -0.8 + index * 0.025, 100 + index, provenance=provenance)
        for index, symbol in enumerate(_background_symbols(25))
    )
    return marker_observations + background


def _request(
    observations: tuple[ProteinProgramObservation, ...],
    *,
    sample_id: str = "sample.property",
    reference_id: str = "reference.control",
) -> ProteinProgramRequest:
    return ProteinProgramRequest(
        sample_id=sample_id,
        observations=observations,
        bootstrap_replicates=16,
        permutation_replicates=64,
        effect_scale="standardized_log2_abundance_contrast",
        effect_reference_id=reference_id,
    )


def _ac(result):
    return next(item for item in result.program_evidence if item.program_id is ExactProgramId.AC)


def test_input_order_and_replay_are_exactly_deterministic() -> None:
    observations = _base_observations()
    request = _request(observations)
    forward = analyze_neftel_protein_programs(request)
    reversed_result = analyze_neftel_protein_programs(_request(tuple(reversed(observations))))
    assert request.request_digest == forward.request_digest
    assert forward == reversed_result
    verification = verify_neftel_protein_program_replay(
        ReplayVerificationRequest(request=request, result=forward)
    )
    assert verification.verified is True


def test_receipt_only_metadata_does_not_reseed_numerical_inference() -> None:
    first = analyze_neftel_protein_programs(
        _request(_base_observations(provenance=SOURCE_A), sample_id="sample.one")
    )
    second = analyze_neftel_protein_programs(
        _request(_base_observations(provenance=SOURCE_B), sample_id="sample.two")
    )
    assert first.request_digest != second.request_digest
    assert first.provenance.computational_digest == second.provenance.computational_digest
    assert first.provenance.bootstrap_seed == second.provenance.bootstrap_seed
    assert first.provenance.rank_permutation_seed == second.provenance.rank_permutation_seed
    assert _ac(first) == _ac(second)


def test_profile_pinned_aliases_share_stochastic_identity_but_not_receipt_identity() -> None:
    wars = _active("WARS", 0.17, 900)
    wars1 = wars.model_copy(update={"gene_symbol": "WARS1"})
    first_request = _request((*_base_observations(), wars))
    second_request = _request((*_base_observations(), wars1))
    profile = algorithm_profile()
    aliases = marker_catalog().aliases

    assert first_request.request_digest != second_request.request_digest
    first_computational = computational_request_digest(
        first_request,
        profile_digest=profile.profile_digest,
        symbol_aliases=aliases,
    )
    second_computational = computational_request_digest(
        second_request,
        profile_digest=profile.profile_digest,
        symbol_aliases=aliases,
    )
    assert first_computational == second_computational
    assert computational_request_digest(
        first_request,
        profile_digest=sha256_digest("different-neftel-profile"),
        symbol_aliases=aliases,
    ) != first_computational

    first = analyze_neftel_protein_programs(first_request)
    second = analyze_neftel_protein_programs(second_request)
    assert first.provenance.computational_digest == second.provenance.computational_digest
    assert first.provenance.bootstrap_seed == second.provenance.bootstrap_seed
    assert first.provenance.rank_permutation_seed == second.provenance.rank_permutation_seed
    assert first.program_evidence == second.program_evidence


@pytest.mark.parametrize(
    "state",
    [ProteinEvidenceState.MISSING, ProteinEvidenceState.UNSUPPORTED],
)
def test_inactive_evidence_changes_counts_but_not_numerical_estimates(
    state: ProteinEvidenceState,
) -> None:
    observations = _base_observations()
    unused_marker = next(
        marker.normalized_symbol
        for marker in marker_catalog().programs["AC"][20:]
        if marker.protein_eligible
    )
    inactive = ProteinProgramObservation(
        observation_id="obs.inactive",
        gene_symbol=unused_marker,
        state=state,
        quality_weight=0.0,
        provenance_digest=SOURCE_A,
    )
    baseline = analyze_neftel_protein_programs(_request(observations))
    augmented = analyze_neftel_protein_programs(_request((*observations, inactive)))
    assert baseline.provenance.computational_digest == augmented.provenance.computational_digest
    assert _ac(baseline).location == _ac(augmented).location
    assert _ac(baseline).rank_enrichment == _ac(augmented).rank_enrichment
    assert _ac(baseline).evidence_counts != _ac(augmented).evidence_counts


def test_left_censoring_is_an_upper_limit_and_never_an_exact_rank_value() -> None:
    observations = _base_observations()
    unused_marker = next(
        marker.normalized_symbol
        for marker in marker_catalog().programs["AC"][20:]
        if marker.protein_eligible
    )
    baseline = analyze_neftel_protein_programs(_request(observations))
    high_limit = _active(
        unused_marker,
        10.0,
        900,
        state=ProteinEvidenceState.LEFT_CENSORED,
    )
    bounded = analyze_neftel_protein_programs(_request((*observations, high_limit)))
    assert _ac(bounded).location.score == _ac(baseline).location.score
    assert _ac(bounded).rank_enrichment.score == _ac(baseline).rank_enrichment.score
    assert _ac(bounded).evidence_counts.left_censored_markers == 1
    assert _ac(bounded).evidence_counts.observed_markers == 12
    censored_driver = next(
        (item for item in _ac(bounded).top_drivers if item.normalized_symbol == unused_marker),
        None,
    )
    if censored_driver is not None:
        assert censored_driver.value_role == "left_censored_upper_limit"


def test_contract_rejects_inactive_numeric_values_and_normalized_alias_duplicates() -> None:
    with pytest.raises(ValidationError, match="cannot carry numeric"):
        ProteinProgramObservation(
            observation_id="obs.bad.missing",
            gene_symbol="CST3",
            state=ProteinEvidenceState.MISSING,
            standardized_effect=-2.0,
            standard_error=0.2,
            quality_weight=0.0,
            provenance_digest=SOURCE_A,
        )
    duplicate_aliases = (
        _active("WARS", 1.0, 1),
        _active("WARS1", 1.0, 2),
    )
    with pytest.raises(ValidationError, match="alias normalization"):
        _request(duplicate_aliases)

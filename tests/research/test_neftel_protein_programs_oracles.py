"""Hand-calculated scientific oracles for Neftel protein-program inference."""

from __future__ import annotations

import math
from itertools import permutations

import pytest
from pydantic import ValidationError

from glio_proteogen.research.neftel_protein_programs import (
    AnalysisSupport,
    ExactProgramId,
    ProgramClassification,
    ProgramFamilyId,
    ProteinEvidenceState,
    ProteinProgramObservation,
    ProteinProgramRequest,
    analyze_neftel_protein_programs,
)
from glio_proteogen.research.neftel_protein_programs.canonical import sha256_digest
from glio_proteogen.research.neftel_protein_programs.catalog import marker_catalog
from glio_proteogen.research.neftel_protein_programs.engine import (
    _benjamini_hochberg,
    _empirical_two_sided_p_value,
    _rank_hypothesis_key,
    _targets,
)
from glio_proteogen.research.neftel_protein_programs.profile import CONSTANTS

SOURCE_DIGEST = sha256_digest("neftel-oracle-source")


def _background_symbols(count: int) -> tuple[str, ...]:
    catalog = marker_catalog()
    program_symbols = {
        marker.normalized_symbol
        for markers in catalog.programs.values()
        for marker in markers
        if marker.protein_eligible
    }
    return tuple(sorted(catalog.protein_background_symbols - program_symbols)[:count])


def _observation(
    symbol: str,
    effect: float,
    *,
    index: int,
    state: ProteinEvidenceState = ProteinEvidenceState.OBSERVED,
    standard_error: float = 0.3,
) -> ProteinProgramObservation:
    return ProteinProgramObservation(
        observation_id=f"obs.{index}",
        gene_symbol=symbol,
        state=state,
        standardized_effect=effect,
        standard_error=standard_error,
        quality_weight=1.0,
        provenance_digest=SOURCE_DIGEST,
    )


def _request(
    marker_count: int,
    *,
    marker_effect: float = 1.0,
    sample_id: str = "sample.oracle",
    source_program: ExactProgramId = ExactProgramId.AC,
) -> ProteinProgramRequest:
    markers = tuple(
        marker.normalized_symbol
        for marker in marker_catalog().programs[source_program]
        if marker.protein_eligible
    )[:marker_count]
    observations = [
        _observation(symbol, marker_effect, index=index)
        for index, symbol in enumerate(markers)
    ]
    observations.extend(
        _observation(symbol, -1.0 + index * 0.02, index=100 + index)
        for index, symbol in enumerate(_background_symbols(25))
    )
    return ProteinProgramRequest(
        sample_id=sample_id,
        observations=tuple(observations),
        bootstrap_replicates=16,
        permutation_replicates=64,
        effect_scale="standardized_log2_abundance_contrast",
        effect_reference_id="reference.control",
    )


def _ac_result(marker_count: int, *, marker_effect: float = 1.0):
    result = analyze_neftel_protein_programs(
        _request(marker_count, marker_effect=marker_effect)
    )
    return next(item for item in result.program_evidence if item.program_id is ExactProgramId.AC)


def test_equal_marker_huber_location_and_rank_have_hand_calculated_values() -> None:
    evidence = _ac_result(12)
    prior = 1.0 / 39.0
    reliability = prior / (0.3**2 + CONSTANTS.standard_error_floor**2)
    expected_location = 12 * reliability / (12 * reliability + CONSTANTS.location_ridge)
    # The 12 tied program markers occupy zero-based ranks 25..36 among 37 proteins.
    expected_rank = 2.0 * ((((25 + 36) / 2.0) / 36.0) - 0.5)
    assert evidence.location.score == pytest.approx(expected_location, abs=1e-6)
    assert evidence.rank_enrichment.score == pytest.approx(expected_rank, abs=1e-6)
    assert evidence.location.effective_sample_size == 12.0
    assert evidence.rank_enrichment.effective_sample_size == 12.0
    assert evidence.location.bootstrap_replicates_used == 16
    assert evidence.rank_enrichment.bootstrap_replicates_used == 16
    assert evidence.rank_enrichment.permutation_replicates_used == 64
    assert evidence.rank_enrichment.p_value == pytest.approx(1.0 / 65.0, abs=1e-6)
    assert evidence.rank_enrichment.q_value is not None
    assert evidence.rank_enrichment.q_value >= evidence.rank_enrichment.p_value
    assert evidence.classification is ProgramClassification.ACTIVATED
    assert evidence.support is AnalysisSupport.SUPPORTED


@pytest.mark.parametrize(
    ("marker_count", "expected_location_support", "expected_program_support"),
    [
        (4, AnalysisSupport.ABSTAINED, AnalysisSupport.ABSTAINED),
        (5, AnalysisSupport.LIMITED, AnalysisSupport.LIMITED),
        (10, AnalysisSupport.LIMITED, AnalysisSupport.LIMITED),
        (12, AnalysisSupport.SUPPORTED, AnalysisSupport.SUPPORTED),
    ],
)
def test_exploratory_and_supported_tiers_are_not_equivalent(
    marker_count: int,
    expected_location_support: AnalysisSupport,
    expected_program_support: AnalysisSupport,
) -> None:
    evidence = _ac_result(marker_count)
    assert evidence.location.support is expected_location_support
    assert evidence.support is expected_program_support
    if expected_location_support is AnalysisSupport.LIMITED:
        assert evidence.location.reason is not None


def test_suppression_requires_an_explicit_reference_standardized_contrast() -> None:
    evidence = _ac_result(12, marker_effect=-1.2)
    assert evidence.classification is ProgramClassification.SUPPRESSED
    with pytest.raises(ValidationError, match="effect_scale"):
        ProteinProgramRequest(
            sample_id="sample.no.reference.scale",
            observations=_request(12).observations,
            bootstrap_replicates=16,
            permutation_replicates=64,
            effect_reference_id="reference.control",
        )
    assert math.isfinite(evidence.location.score or math.nan)


def test_empirical_p_value_matches_an_exhaustive_four_protein_permutation_oracle() -> None:
    # This integer statistic is six times a 1:2 reliability-weighted percentile
    # mean centered on the four-protein background mean.  All 4! assignments are
    # enumerated independently of the engine's random permutation generator.
    background_ranks = (0, 1, 2, 3)

    def scaled_centered_statistic(assignment: tuple[int, ...]) -> float:
        return float(2 * (assignment[0] + 2 * assignment[1]) - 9)

    observed = scaled_centered_statistic(background_ranks)
    exhaustive_null = [
        scaled_centered_statistic(assignment)
        for assignment in permutations(background_ranks)
    ]
    assert len(exhaustive_null) == 24
    assert sum(abs(value) >= abs(observed) for value in exhaustive_null) == 12
    assert _empirical_two_sided_p_value(observed, exhaustive_null) == pytest.approx(
        13.0 / 25.0
    )
    assert _empirical_two_sided_p_value(-observed, exhaustive_null) == pytest.approx(
        13.0 / 25.0
    )
    with pytest.raises(ValueError, match="at least one"):
        _empirical_two_sided_p_value(observed, [])


def test_benjamini_hochberg_ties_and_monotonicity_match_hand_oracle() -> None:
    p_values: dict[object, float] = {
        "first_tie": 0.01,
        "second_tie": 0.01,
        "middle": 0.04,
        "large": 0.20,
        "unit": 1.0,
    }
    adjusted = _benjamini_hochberg(p_values)
    assert adjusted == pytest.approx(
        {
            "first_tie": 0.025,
            "second_tie": 0.025,
            "middle": 1.0 / 15.0,
            "large": 0.25,
            "unit": 1.0,
        }
    )
    ordered = sorted(p_values, key=lambda identifier: p_values[identifier])
    assert [adjusted[identifier] for identifier in ordered] == sorted(
        adjusted[identifier] for identifier in ordered
    )
    assert all(adjusted[identifier] >= p_value for identifier, p_value in p_values.items())
    assert _benjamini_hochberg({}) == {}


def test_alias_program_labels_share_one_numerical_rank_hypothesis() -> None:
    grouped: dict[tuple[tuple[str, float], ...], list[object]] = {}
    for target in _targets():
        grouped.setdefault(_rank_hypothesis_key(target), []).append(target.program_id)
    duplicate_groups = {
        frozenset(identifiers)
        for identifiers in grouped.values()
        if len(identifiers) > 1
    }
    assert len(grouped) == 11
    assert duplicate_groups == {
        frozenset((ExactProgramId.AC, ProgramFamilyId.ASTROCYTE_LIKE)),
        frozenset(
            (
                ExactProgramId.OPC,
                ProgramFamilyId.OLIGODENDROCYTE_PROGENITOR_LIKE,
            )
        ),
    }

    ac_result = analyze_neftel_protein_programs(_request(12))
    ac_by_identifier = {item.program_id: item for item in ac_result.program_evidence}
    ac = ac_by_identifier[ExactProgramId.AC].rank_enrichment
    astrocyte = ac_by_identifier[ProgramFamilyId.ASTROCYTE_LIKE].rank_enrichment
    opc_result = analyze_neftel_protein_programs(
        _request(12, source_program=ExactProgramId.OPC)
    )
    opc_by_identifier = {item.program_id: item for item in opc_result.program_evidence}
    opc = opc_by_identifier[ExactProgramId.OPC].rank_enrichment
    oligodendrocyte = opc_by_identifier[
        ProgramFamilyId.OLIGODENDROCYTE_PROGENITOR_LIKE
    ].rank_enrichment

    assert ac.p_value is not None
    assert ac.p_value == astrocyte.p_value
    assert ac.q_value == astrocyte.q_value
    assert ac.null_standard_deviation == astrocyte.null_standard_deviation
    assert opc.p_value is not None
    assert opc.p_value == oligodendrocyte.p_value
    assert opc.q_value == oligodendrocyte.q_value
    assert opc.null_standard_deviation == oligodendrocyte.null_standard_deviation

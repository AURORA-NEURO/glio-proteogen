from __future__ import annotations

import math
from typing import cast

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm_neftel_transition.contracts import (
    AnalysisSupport,
    ConditionalTransitionClassification,
    LongitudinalGbmNeftelTransitionRequest,
    LongitudinalGbmNeftelTransitionResult,
    ProteinEvidenceState,
    ProteinObservation,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.demo import (
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.engine import (
    _active_pairs,
    _is_reliable,
    _quantize,
    _solver_evidence,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.fitted_catalog import (
    neftel_program_fitted_catalog,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.service import (
    analyze_longitudinal_gbm_neftel_transition,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.solver import (
    solve_conditional_coordinates,
)


def _validated_observation(
    observation: ProteinObservation,
    *,
    state: ProteinEvidenceState,
    log_abundance: float,
    standard_error: float,
) -> ProteinObservation:
    document = observation.model_dump(mode="python")
    document.update(
        state=state,
        log_abundance=log_abundance,
        standard_error=standard_error,
        quality_weight=1.0,
    )
    return ProteinObservation.model_validate(document, strict=True)


def _one_exact_plus_loose_censors(
    upper_limit: float,
) -> LongitudinalGbmNeftelTransitionRequest:
    request = synthetic_demo_request()
    points = []
    for point_index, point in enumerate(request.time_points[:2]):
        observations = []
        for observation in point.observations:
            is_exact = point_index == 0 or observation.gene_symbol == "FTL"
            observations.append(
                _validated_observation(
                    observation,
                    state=(
                        ProteinEvidenceState.OBSERVED
                        if is_exact
                        else ProteinEvidenceState.LEFT_CENSORED
                    ),
                    log_abundance=0.0 if is_exact else upper_limit,
                    standard_error=0.1,
                )
            )
        points.append(point.model_copy(update={"observations": tuple(observations)}))
    return request.model_copy(update={"time_points": tuple(points), "bootstrap_replicates": 32})


def _balanced_mes2_request() -> tuple[LongitudinalGbmNeftelTransitionRequest, np.ndarray]:
    catalog = neftel_program_fitted_catalog()
    mes2 = catalog.programs[0]
    positions = np.asarray(mes2.member_local_indices, dtype=np.int64)
    standard_error = 0.01
    delta_standard_error = math.sqrt(2.0) * standard_error
    reliability = 1.0 / (1.0 + (delta_standard_error / catalog.reference_scale[positions]) ** 2)

    # A nonzero vector in the weighted design null space gives exact opposing
    # MES2 member contributions while every fitted coordinate remains zero.
    weighted_design = catalog.reference_design[positions].T * reliability
    _, _, right_vectors = np.linalg.svd(weighted_design, full_matrices=True)
    standardized_delta = right_vectors[-1]
    standardized_delta *= 0.2 / float(np.max(np.abs(standardized_delta)))
    assert np.max(np.abs(weighted_design @ standardized_delta)) < 1.0e-12

    raw_delta = np.zeros(catalog.union_feature_count, dtype=np.float64)
    raw_delta[positions] = standardized_delta * catalog.reference_scale[positions]
    local_position = {
        gene_symbol: index for index, gene_symbol in enumerate(catalog.union_gene_symbols)
    }
    request = synthetic_demo_request()
    points = []
    for point_index, point in enumerate(request.time_points[:2]):
        observations = tuple(
            _validated_observation(
                observation,
                state=ProteinEvidenceState.OBSERVED,
                log_abundance=(
                    0.0
                    if point_index == 0
                    else float(raw_delta[local_position[observation.gene_symbol]])
                ),
                standard_error=standard_error,
            )
            for observation in point.observations
        )
        points.append(point.model_copy(update={"observations": observations}))
    return (
        request.model_copy(update={"time_points": tuple(points), "bootstrap_replicates": 32}),
        standardized_delta,
    )


@pytest.fixture(scope="module")
def analyzed_demo_pair() -> tuple[
    LongitudinalGbmNeftelTransitionRequest,
    LongitudinalGbmNeftelTransitionResult,
]:
    request = synthetic_demo_request()
    request = request.model_copy(
        update={"time_points": request.time_points[:2], "bootstrap_replicates": 32}
    )
    return request, analyze_longitudinal_gbm_neftel_transition(request)


def test_nonbinding_censor_population_is_admitted_but_cannot_manufacture_support() -> None:
    loose = analyze_longitudinal_gbm_neftel_transition(
        _one_exact_plus_loose_censors(50.0)
    ).transitions[0]
    looser = analyze_longitudinal_gbm_neftel_transition(
        _one_exact_plus_loose_censors(100.0)
    ).transitions[0]

    for transition in (loose, looser):
        global_result = transition.global_transition
        assert global_result.support is AnalysisSupport.ABSTAINED
        assert global_result.admitted_active_gene_count == 256
        assert global_result.shared_active_gene_count == 1
        assert global_result.observed_count == 1
        assert global_result.left_censored_count == 0
        assert global_result.admitted_left_censored_count == 255

        mes2 = transition.programs[0]
        assert mes2.program_id == "MES2"
        assert mes2.support is AnalysisSupport.ABSTAINED
        assert mes2.admitted_active_feature_count == 40
        assert mes2.active_feature_count == 1
        assert mes2.observed_count == 1
        assert mes2.left_censored_count == 0
        assert mes2.admitted_left_censored_count == 39

    assert looser.global_transition.support is loose.global_transition.support
    assert looser.global_transition.shared_active_gene_count == (
        loose.global_transition.shared_active_gene_count
    )
    assert looser.global_transition.coefficient_mass_coverage == (
        loose.global_transition.coefficient_mass_coverage
    )
    assert looser.programs[0].support is loose.programs[0].support
    assert looser.programs[0].active_feature_count == loose.programs[0].active_feature_count
    assert looser.programs[0].coefficient_mass_coverage == (
        loose.programs[0].coefficient_mass_coverage
    )


def test_zero_coordinate_preserves_balanced_positive_negative_mes2_discordance() -> None:
    request, standardized_delta = _balanced_mes2_request()
    mes2 = analyze_longitudinal_gbm_neftel_transition(request).transitions[0].programs[0]

    assert np.any(standardized_delta > 0.0)
    assert np.any(standardized_delta < 0.0)
    assert mes2.support is AnalysisSupport.LIMITED
    assert mes2.score == 0.0
    assert mes2.discordance is not None
    assert mes2.discordance >= 0.99
    assert any(item.conditional_contribution > 0.0 for item in mes2.top_contributions)
    assert any(item.conditional_contribution < 0.0 for item in mes2.top_contributions)


def test_demo_top_contribution_ablations_are_true_omit_one_refits(
    analyzed_demo_pair: tuple[
        LongitudinalGbmNeftelTransitionRequest,
        LongitudinalGbmNeftelTransitionResult,
    ],
) -> None:
    request, result = analyzed_demo_pair
    catalog = neftel_program_fitted_catalog()
    active = _active_pairs(request, 0, catalog)
    reliable_active = tuple(
        pair
        for pair in active
        if _is_reliable(pair, float(catalog.reference_scale[pair.local_position]))
    )
    point = solve_conditional_coordinates(
        catalog.reference_design,
        _solver_evidence(reliable_active, catalog.reference_scale),
    )
    position_by_gene = {pair.gene_symbol: pair.local_position for pair in reliable_active}

    for reported, fitted in zip(
        result.transitions[0].programs,
        catalog.programs,
        strict=True,
    ):
        assert reported.support is AnalysisSupport.LIMITED
        assert reported.top_contributions
        assert len(reported.ablations.top_contributions) == len(reported.top_contributions)
        for contribution, ablation in zip(
            reported.top_contributions,
            reported.ablations.top_contributions,
            strict=True,
        ):
            assert ablation.component_kind == "top_contribution"
            assert ablation.component_id == contribution.gene_symbol
            assert ablation.removed_feature_count == 1
            assert ablation.support is AnalysisSupport.LIMITED

            removed_position = position_by_gene[contribution.gene_symbol]
            remaining = tuple(
                pair for pair in reliable_active if pair.local_position != removed_position
            )
            omitted = solve_conditional_coordinates(
                catalog.reference_design,
                _solver_evidence(remaining, catalog.reference_scale),
                initial_coordinates=point.coordinates,
            )
            without = (
                float(omitted.coordinates[fitted.program_index + 1]) / fitted.cross_fitted_mad_scale
            )
            assert ablation.conditional_score_without_component == _quantize(without)
            assert ablation.score_delta == _quantize(cast("float", reported.score) - without)

        leave_out = reported.ablations.leave_program_out
        assert leave_out is not None
        assert leave_out.component_kind == "leave_program_out"
        assert leave_out.component_id == reported.program_id
        assert leave_out.support is AnalysisSupport.ABSTAINED
        assert (
            leave_out.classification_without_component
            is ConditionalTransitionClassification.NOT_ESTIMABLE
        )
        assert leave_out.conditional_score_without_component is None
        assert leave_out.score_delta is None
        assert leave_out.reason is not None
        assert "held-marker reconstruction fields" in leave_out.reason
        assert reported.request_reconstruction_evaluable_fold_count > 0
        assert reported.request_reconstruction_median_relative_gain is not None

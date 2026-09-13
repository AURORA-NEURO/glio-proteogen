"""Scientific invariants for the fitted GBM complex-transition runtime."""

from __future__ import annotations

import pytest

from glio_proteogen.research.longitudinal_gbm_complex_transition import engine as engine_module
from glio_proteogen.research.longitudinal_gbm_complex_transition.contracts import (
    AnalysisSupport,
    ComplexTransitionClassification,
    LongitudinalGbmComplexTransitionRequest,
    LongitudinalTimePoint,
    ProteinEvidenceState,
    ProteinObservation,
    UncertaintyState,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.demo import (
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.engine import (
    infer_longitudinal_gbm_complex_transition,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.errors import (
    ComplexTransitionInferenceError,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.fitted_catalog import (
    complex_transition_fitted_catalog,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.profile import (
    algorithm_profile,
)


def _request_with_points(
    points: tuple[LongitudinalTimePoint, ...],
    *,
    series_id: str,
) -> LongitudinalGbmComplexTransitionRequest:
    demo = synthetic_demo_request()
    return LongitudinalGbmComplexTransitionRequest(
        series_id=series_id,
        assay_compatibility=demo.assay_compatibility,
        normalization_reference=demo.normalization_reference,
        time_points=points,
        bootstrap_replicates=32,
    )


def _demo_32(*, reverse_observations: bool = False) -> LongitudinalGbmComplexTransitionRequest:
    demo = synthetic_demo_request()
    points = tuple(
        LongitudinalTimePoint(
            time_point_id=point.time_point_id,
            time_offset_days=point.time_offset_days,
            normalization_reference_digest=point.normalization_reference_digest,
            observations=(
                tuple(reversed(point.observations)) if reverse_observations else point.observations
            ),
        )
        for point in demo.time_points
    )
    return _request_with_points(points, series_id=demo.series_id)


def _censored_request(
    state_at_second_point: ProteinEvidenceState,
) -> LongitudinalGbmComplexTransitionRequest:
    catalog = complex_transition_fitted_catalog()
    demo = synthetic_demo_request()
    model = catalog.complexes[0]
    symbols = tuple(catalog.source_catalog.genes[index] for index in model.member_feature_indices)

    def observations(point_index: int) -> tuple[ProteinObservation, ...]:
        result: list[ProteinObservation] = []
        for member_index, symbol in enumerate(symbols):
            state = ProteinEvidenceState.OBSERVED if point_index == 0 else state_at_second_point
            active = state in {
                ProteinEvidenceState.OBSERVED,
                ProteinEvidenceState.LEFT_CENSORED,
            }
            result.append(
                ProteinObservation(
                    observation_id=f"censor.{point_index}.{member_index}",
                    gene_symbol=symbol,
                    state=state,
                    log_abundance=(0.0 if point_index == 0 else 0.5) if active else None,
                    standard_error=0.01 if active else None,
                    quality_weight=1.0 if active else 0.0,
                    provenance_digest=demo.time_points[0].observations[0].provenance_digest,
                )
            )
        return tuple(result)

    points = (
        LongitudinalTimePoint(
            time_point_id="censor.baseline",
            time_offset_days=0.0,
            normalization_reference_digest=demo.normalization_reference.binding_digest,
            observations=observations(0),
        ),
        LongitudinalTimePoint(
            time_point_id="censor.followup",
            time_offset_days=30.0,
            normalization_reference_digest=demo.normalization_reference.binding_digest,
            observations=observations(1),
        ),
    )
    return _request_with_points(
        points,
        series_id=f"synthetic-{state_at_second_point.value}-bounds",
    )


def test_profile_binds_real_patient_grouped_evaluation_and_claim_ceiling() -> None:
    profile = algorithm_profile()
    evaluation = profile.evaluation

    assert profile.counts.strict_patient_pair_count == 104
    assert profile.counts.complex_count == 28
    assert len({item.domain_id for item in profile.complexes}) == 11
    assert evaluation.patient_count == 104
    assert evaluation.evaluation_count == 14_988
    assert evaluation.factor_model_mean_standardized_mae == pytest.approx(0.6989814224)
    assert evaluation.training_center_mean_standardized_mae == pytest.approx(0.8769685109)
    assert evaluation.factor_model_mean_standardized_mae < (
        evaluation.training_center_mean_standardized_mae
    )
    assert evaluation.held_member_direction_accuracy == pytest.approx(0.7255137443)
    assert evaluation.patient_cluster_median_gain_90_interval[0] > 0.0
    assert evaluation.external_validation_performed is False
    assert profile.constants.minimum_member_reliability == 0.05
    assert profile.claim_ceiling.endswith("participant_set_transition_concordance_only")


def test_runtime_is_deterministic_and_observation_order_invariant() -> None:
    ordered = infer_longitudinal_gbm_complex_transition(_demo_32())
    reversed_result = infer_longitudinal_gbm_complex_transition(_demo_32(reverse_observations=True))

    assert ordered == reversed_result
    assert ordered.request_digest == _demo_32().request_digest
    assert len(ordered.transitions) == 2
    assert all(len(transition.complexes) == 28 for transition in ordered.transitions)
    estimated = tuple(
        item
        for transition in ordered.transitions
        for item in transition.complexes
        if item.support is not AnalysisSupport.ABSTAINED
    )
    assert estimated
    assert all(item.solver_converged is True for item in estimated)
    assert all(item.solver_objective_monotone is True for item in estimated)
    assert all(
        item.solver_final_objective <= item.solver_initial_objective
        for item in estimated
        if item.solver_final_objective is not None and item.solver_initial_objective is not None
    )
    assert all(item.uncertainty.state is UncertaintyState.ESTIMATED for item in estimated)
    for item in estimated:
        assert item.lower_bound is not None
        assert item.score is not None
        assert item.upper_bound is not None
        assert item.lower_bound <= item.score <= item.upper_bound


def test_one_sided_only_evidence_abstains_instead_of_becoming_false_stability() -> None:
    result = infer_longitudinal_gbm_complex_transition(
        _censored_request(ProteinEvidenceState.LEFT_CENSORED)
    )
    first = result.transitions[0].complexes[0]

    assert first.support is AnalysisSupport.ABSTAINED
    assert first.observed_member_count == 0
    assert first.left_censored_member_count == first.active_member_count
    assert first.score is None
    assert first.classification is ComplexTransitionClassification.NOT_ESTIMABLE
    assert first.top_contributions == ()
    assert first.least_source_aligned_observed_member is None
    assert "one-sided-only" in first.limitations[0]


def test_uncertainty_uses_paired_empirical_covariance_and_honest_closure() -> None:
    bootstrap = engine_module._BootstrapCoordinates(
        measurement=(1.0, 2.0, 4.0),
        fitted_model=(2.0, 0.0, 3.0),
        combined=(4.0, 1.0, 8.0),
        failed_replicates=0,
    )

    uncertainty = engine_module._uncertainty(bootstrap)

    assert uncertainty.measurement_model_covariance == pytest.approx(7.0 / 6.0)
    assert uncertainty.variance_closure_residual == pytest.approx(16.0 / 3.0)
    assert uncertainty.variance_closure_residual is not None
    assert uncertainty.variance_closure_residual > 0.0
    assert engine_module._sample_covariance((1.0,), (2.0,)) == 0.0
    with pytest.raises(ComplexTransitionInferenceError, match="unequal lengths"):
        engine_module._sample_covariance((1.0,), (2.0, 3.0))


def test_negligible_absolute_quality_abstains_before_driver_serialization() -> None:
    request = _censored_request(ProteinEvidenceState.OBSERVED)
    points = tuple(
        point.model_copy(
            update={
                "observations": tuple(
                    observation.model_copy(update={"quality_weight": 1.0e-12})
                    for observation in point.observations
                )
            }
        )
        for point in request.time_points
    )

    result = infer_longitudinal_gbm_complex_transition(
        request.model_copy(update={"time_points": points})
    )
    first = result.transitions[0].complexes[0]

    assert first.support is AnalysisSupport.ABSTAINED
    assert first.classification is ComplexTransitionClassification.NOT_ESTIMABLE
    assert first.coefficient_mass_coverage == 0.0
    assert any("effective-reliability" in reason for reason in first.limitations)
    assert any("quality-adjusted" in reason for reason in first.limitations)


def test_epsilon_weight_third_member_cannot_unlock_three_member_support() -> None:
    request = _censored_request(ProteinEvidenceState.OBSERVED)
    points = tuple(
        point.model_copy(
            update={
                "observations": tuple(
                    observation.model_copy(
                        update={"quality_weight": 1.0 if index < 2 else 1.0e-12}
                    )
                    for index, observation in enumerate(point.observations)
                )
            }
        )
        for point in request.time_points
    )

    result = infer_longitudinal_gbm_complex_transition(
        request.model_copy(update={"time_points": points})
    )
    first = result.transitions[0].complexes[0]

    assert first.support is AnalysisSupport.ABSTAINED
    assert first.classification is ComplexTransitionClassification.NOT_ESTIMABLE
    assert any("effective-reliability" in reason for reason in first.limitations)


def test_one_negligible_member_is_omitted_without_crashing_a_supported_solve() -> None:
    request = _censored_request(ProteinEvidenceState.OBSERVED)
    points = tuple(
        point.model_copy(
            update={
                "observations": tuple(
                    observation.model_copy(
                        update={"quality_weight": 1.0e-12 if index == 0 else 1.0}
                    )
                    for index, observation in enumerate(point.observations)
                )
            }
        )
        for point in request.time_points
    )

    result = infer_longitudinal_gbm_complex_transition(
        request.model_copy(update={"time_points": points})
    )
    first = result.transitions[0].complexes[0]

    assert first.support is not AnalysisSupport.ABSTAINED
    assert all(item.gene_symbol != "EGFR" for item in first.top_contributions)


@pytest.mark.parametrize(
    "state",
    [ProteinEvidenceState.MISSING, ProteinEvidenceState.UNSUPPORTED],
)
def test_missing_and_unsupported_members_force_abstention_not_negative_scores(
    state: ProteinEvidenceState,
) -> None:
    result = infer_longitudinal_gbm_complex_transition(_censored_request(state))
    first = result.transitions[0].complexes[0]

    assert first.support is AnalysisSupport.ABSTAINED
    assert first.classification is ComplexTransitionClassification.NOT_ESTIMABLE
    assert first.score is None
    assert first.active_member_count == 0
    assert first.top_contributions == ()
    assert "fewer than three" in first.limitations[0]


def test_active_symbol_outside_locked_source_axis_is_rejected() -> None:
    request = _demo_32()
    first_point = request.time_points[0]
    first = first_point.observations[0]
    forged = ProteinObservation(
        observation_id=first.observation_id,
        gene_symbol="NOTAREALGENE",
        state=first.state,
        log_abundance=first.log_abundance,
        standard_error=first.standard_error,
        quality_weight=first.quality_weight,
        provenance_digest=first.provenance_digest,
    )
    point = LongitudinalTimePoint(
        time_point_id=first_point.time_point_id,
        time_offset_days=first_point.time_offset_days,
        normalization_reference_digest=first_point.normalization_reference_digest,
        observations=(forged, *first_point.observations[1:]),
    )
    forged_request = _request_with_points(
        (point, *request.time_points[1:]),
        series_id="synthetic-unknown-active-symbol",
    )

    with pytest.raises(ComplexTransitionInferenceError, match="outside the locked"):
        infer_longitudinal_gbm_complex_transition(forged_request)

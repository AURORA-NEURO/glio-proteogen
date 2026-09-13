from __future__ import annotations

import math
from dataclasses import replace
from itertools import pairwise

import numpy as np
import pytest

import glio_proteogen.research.longitudinal_gbm.engine as engine_module
from glio_proteogen.research.longitudinal_gbm.catalog import longitudinal_gbm_catalog
from glio_proteogen.research.longitudinal_gbm.contracts import (
    AnalysisSupport,
    LongitudinalGbmRequest,
    ProteinEvidenceState,
    ProteinObservation,
    TransitionClassification,
)
from glio_proteogen.research.longitudinal_gbm.demo import synthetic_demo_request
from glio_proteogen.research.longitudinal_gbm.engine import (
    brute_force_segmentation,
    exact_pelt_segmentation,
    heteroscedastic_huber_segment_cost,
    infer_longitudinal_gbm,
    pelt_candidate_counts,
)
from glio_proteogen.research.longitudinal_gbm.errors import (
    LongitudinalInferenceError,
    SourceProfileIntegrityError,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceDeadlineExceededError,
)


@pytest.fixture(scope="module")
def demo_result():
    return infer_longitudinal_gbm(synthetic_demo_request())


def _replace_request(document: dict[str, object]) -> LongitudinalGbmRequest:
    return LongitudinalGbmRequest.model_validate(document)


def test_demo_is_locked_deterministic_and_interval_classified(demo_result) -> None:
    replay = infer_longitudinal_gbm(synthetic_demo_request())
    assert replay == demo_result
    assert tuple(item.classification for item in demo_result.transitions) == (
        TransitionClassification.SOURCE_RECURRENCE_ALIGNED,
        TransitionClassification.REVERSE_ALIGNED,
        TransitionClassification.STABLE,
    )
    interaction_covariances: list[float] = []
    for transition in demo_result.transitions:
        assert transition.support is AnalysisSupport.LIMITED
        assert transition.abstention_reasons == (
            "fewer than 64 estimable bootstrap projections for fully supported uncertainty",
        )
        assert transition.lower_bound <= transition.score <= transition.upper_bound
        assert transition.bootstrap_replicates_used == 32
        assert transition.measurement_uncertainty.standard_error > 0.0
        assert transition.coefficient_uncertainty.standard_error > 0.0
        interaction = transition.uncertainty_interaction
        assert interaction.covariance is not None
        interaction_covariances.append(interaction.covariance)
        assert interaction.variance_contribution == pytest.approx(2.0 * interaction.covariance)
        assert interaction.combined_variance is not None
        expected_receipt_residual = engine_module._quantize(
            abs(
                interaction.combined_variance
                - (
                    transition.measurement_uncertainty.standard_error**2
                    + transition.coefficient_uncertainty.standard_error**2
                    + interaction.variance_contribution
                )
            )
        )
        assert interaction.decomposition_residual == expected_receipt_residual
        assert interaction.combined_variance == pytest.approx(
            transition.measurement_uncertainty.standard_error**2
            + transition.coefficient_uncertainty.standard_error**2
            + interaction.variance_contribution,
            abs=1e-6,
        )
        assert transition.top_drivers
        assert transition.top_driver_ablations
        assert transition.source_processing_ablations[0].support is AnalysisSupport.LIMITED
        assert "caller observations unchanged" in (
            transition.source_processing_ablations[0].comparison
        )
        assert "not an independent model validation" in (
            transition.source_processing_ablations[0].reason
        )
    assert any(covariance < 0.0 for covariance in interaction_covariances)
    assert demo_result.pelt_analysis is not None
    assert demo_result.pelt_analysis.method == (
        "exact_pelt_duration_normalized_transition_rate_huber_v2"
    )
    assert demo_result.pelt_analysis.support is AnalysisSupport.LIMITED
    assert not demo_result.pelt_analysis.boundaries
    assert "fewer than 64 joint bootstrap rate paths" in demo_result.pelt_analysis.reason
    assert "duration-normalized transition rates" in demo_result.limitations[-1]


def test_classification_uses_only_interval() -> None:
    classify = engine_module._classification
    assert classify(0.25, 2.0) is TransitionClassification.SOURCE_RECURRENCE_ALIGNED
    assert classify(-2.0, -0.25) is TransitionClassification.REVERSE_ALIGNED
    assert classify(-0.05, 0.05) is TransitionClassification.STABLE
    assert classify(-0.2, 0.8) is TransitionClassification.INDETERMINATE


def test_one_sided_huber_bounds_do_not_impute_latent_abundance() -> None:
    exact = ((0.8, "exact_delta", 1.0), (1.0, "exact_delta", 1.0))
    upper_nonbinding = ((10.0, "upper_bound", 1.0),) * 4
    lower_nonbinding = ((-10.0, "lower_bound", 1.0),) * 4
    upper_binding = ((-0.8, "upper_bound", 1.0),) * 4
    lower_binding = ((0.8, "lower_bound", 1.0),) * 4
    assert 0.8 < engine_module._robust_concordance_location(exact) < 1.0
    assert abs(engine_module._robust_concordance_location(upper_nonbinding)) < 1e-6
    assert abs(engine_module._robust_concordance_location(lower_nonbinding)) < 1e-6
    assert engine_module._robust_concordance_location(upper_binding) < -0.79
    assert engine_module._robust_concordance_location(lower_binding) > 0.79
    assert engine_module._aligned_semantics("upper_bound", -1.0) == "lower_bound"
    assert engine_module._aligned_semantics("lower_bound", -1.0) == "upper_bound"


def test_nonbinding_censor_limits_are_stable_not_manufactured_direction() -> None:
    request = synthetic_demo_request()
    catalog = longitudinal_gbm_catalog()
    first = request.time_points[0]
    second = request.time_points[1]
    left: list[ProteinObservation] = []
    right: list[ProteinObservation] = []
    for source_left, source_right in zip(first.observations, second.observations, strict=True):
        feature = catalog.features_by_symbol[source_left.gene_symbol]
        baseline = 10.0
        if feature.ensemble_mean_coefficient >= 0.0:
            left_state = ProteinEvidenceState.OBSERVED
            right_state = ProteinEvidenceState.LEFT_CENSORED
            left_value, right_value = baseline, baseline + 10.0 * feature.transition_scale
        else:
            left_state = ProteinEvidenceState.LEFT_CENSORED
            right_state = ProteinEvidenceState.OBSERVED
            left_value, right_value = baseline, baseline - 10.0 * feature.transition_scale
        left.append(
            source_left.model_copy(update={"state": left_state, "log_abundance": left_value})
        )
        right.append(
            source_right.model_copy(update={"state": right_state, "log_abundance": right_value})
        )
    limited_request = LongitudinalGbmRequest(
        series_id="synthetic.censor.nonbinding",
        assay_compatibility=request.assay_compatibility,
        normalization_reference=request.normalization_reference,
        time_points=(
            first.model_copy(update={"observations": tuple(left)}),
            second.model_copy(update={"observations": tuple(right)}),
        ),
        bootstrap_replicates=32,
    )
    transition = infer_longitudinal_gbm(limited_request).transitions[0]
    assert transition.classification is TransitionClassification.STABLE
    assert abs(transition.score) < 0.01
    assert all(
        driver.value_semantics in {"upper_bound", "lower_bound"}
        for driver in transition.top_drivers
    )


def test_shared_timepoint_draw_is_reused_across_adjacent_edges() -> None:
    request = synthetic_demo_request()
    catalog = longitudinal_gbm_catalog()
    numerical = engine_module.computational_request_digest(
        request,
        profile_digest=catalog.content_digest,
    )
    selected = engine_module._selected_replicates(catalog, numerical, 32)
    active_left = engine_module._active_pairs(request, 0, catalog)
    active_right = engine_module._active_pairs(request, 1, catalog)
    draws_left = engine_module._draw_delta_evidence(active_left, numerical, selected)
    draws_right = engine_module._draw_delta_evidence(active_right, numerical, selected)
    common = sorted(
        {pair.feature.gene_symbol for pair in active_left}
        & {pair.feature.gene_symbol for pair in active_right}
    )
    symbol = common[0]
    left_column = next(
        i for i, pair in enumerate(active_left) if pair.feature.gene_symbol == symbol
    )
    right_column = next(
        i for i, pair in enumerate(active_right) if pair.feature.gene_symbol == symbol
    )
    replicate = selected[0]
    points = request.time_points
    sampled = []
    for point_index in range(3):
        observation = next(
            item for item in points[point_index].observations if item.gene_symbol == symbol
        )
        generator = engine_module.np.random.default_rng(
            engine_module._stream_seed(
                numerical,
                f"measurement:{replicate.replicate_digest}:{point_index}:{symbol}",
            )
        )
        sampled.append(engine_module._sample_reported_log_value(observation, generator))
    assert draws_left[0, left_column] == pytest.approx(sampled[1] - sampled[0])
    assert draws_right[0, right_column] == pytest.approx(sampled[2] - sampled[1])
    assert draws_left[0, left_column] + draws_right[0, right_column] == pytest.approx(
        sampled[2] - sampled[0]
    )


def test_observation_order_and_opaque_identifier_changes_preserve_numbers(demo_result) -> None:
    request = synthetic_demo_request()
    reordered = request.model_copy(
        update={
            "time_points": tuple(
                point.model_copy(update={"observations": tuple(reversed(point.observations))})
                for point in request.time_points
            )
        }
    )
    assert infer_longitudinal_gbm(reordered) == demo_result

    document = request.model_dump(mode="python")
    for point_index, point in enumerate(document["time_points"]):
        for observation_index, observation in enumerate(point["observations"]):
            observation["observation_id"] = f"renamed.{point_index}.{observation_index}"
            observation["provenance_digest"] = "sha256:" + f"{observation_index + 1:064x}"[-64:]
    renamed = _replace_request(document)
    changed = infer_longitudinal_gbm(renamed)
    assert changed.request_digest != demo_result.request_digest
    assert changed.provenance.numerical_seed_digest == demo_result.provenance.numerical_seed_digest
    assert tuple((t.score, t.lower_bound, t.upper_bound) for t in changed.transitions) == tuple(
        (t.score, t.lower_bound, t.upper_bound) for t in demo_result.transitions
    )
    assert changed.pelt_analysis == demo_result.pelt_analysis


def test_unknown_active_symbol_fails_closed_but_sparse_supported_symbol_abstains() -> None:
    request = synthetic_demo_request()
    document = request.model_dump(mode="python")
    document["time_points"] = document["time_points"][:2]
    document["time_points"][0]["observations"][0]["gene_symbol"] = "NOTAREALGENE"
    unknown = _replace_request(document)
    with pytest.raises(LongitudinalInferenceError, match="outside the frozen"):
        infer_longitudinal_gbm(unknown)

    sparse_document = request.model_dump(mode="python")
    sparse_document["time_points"] = sparse_document["time_points"][:3]
    for point in sparse_document["time_points"]:
        point["observations"] = point["observations"][:1]
    sparse = _replace_request(sparse_document)
    result = infer_longitudinal_gbm(sparse)
    assert all(item.support is AnalysisSupport.ABSTAINED for item in result.transitions)
    assert result.pelt_analysis is None


def test_engine_rechecks_assay_compatibility_for_direct_unvalidated_callers() -> None:
    request = synthetic_demo_request()
    incompatible = request.assay_compatibility.model_copy(
        update={"assay": "label_free_mass_spectrometry"}
    )
    bypassed = request.model_copy(update={"assay_compatibility": incompatible})
    with pytest.raises(LongitudinalInferenceError, match="assay compatibility attestation"):
        infer_longitudinal_gbm(bypassed)


def test_pelt_matches_bruteforce_and_actually_prunes() -> None:
    values = (0.0, 0.0, 0.0, 4.0, 4.0, 4.0, -2.0, -2.0)
    errors = (0.2,) * len(values)
    exact = exact_pelt_segmentation(values, errors, 2.0)
    brute = brute_force_segmentation(values, errors, 2.0)
    assert exact[0] == brute[0] == (3, 6)
    assert exact[1] == pytest.approx(brute[1])
    counts = pelt_candidate_counts(values, errors, 2.0)
    assert counts == (1, 1, 2, 3, 4, 3, 3, 4)
    assert any(current < previous + 1 for previous, current in pairwise(counts))


def test_duration_normalized_rates_do_not_segment_constant_rate_trajectories() -> None:
    request = synthetic_demo_request()
    template = request.time_points[0]
    offsets = (0.0, 30.0, 90.0, 180.0, 300.0, 450.0, 630.0)
    points = tuple(
        template.model_copy(update={"time_point_id": f"rate.{index}", "time_offset_days": offset})
        for index, offset in enumerate(offsets)
    )
    rate_request = request.model_copy(update={"time_points": points})
    durations = tuple(right - left for left, right in pairwise(offsets))
    transitions = tuple(0.5 * duration / 90.0 for duration in durations)
    rates = engine_module._duration_normalized_rates(rate_request, transitions)
    assert rates == pytest.approx((0.5,) * len(transitions))
    assert exact_pelt_segmentation(rates, (0.1,) * len(rates), 3.0)[0] == ()

    step_rates = (0.0, 0.0, 2.0, 2.0, -1.0, -1.0)
    assert exact_pelt_segmentation(step_rates, (0.1,) * 6, 3.0)[0] == (2, 4)

    with pytest.raises(ValueError, match="exactly one value"):
        engine_module._duration_normalized_rates(rate_request, transitions[:-1])
    invalid_points = list(points)
    invalid_points[1] = invalid_points[1].model_copy(update={"time_offset_days": 0.0})
    invalid_request = rate_request.model_copy(update={"time_points": tuple(invalid_points)})
    with pytest.raises(LongitudinalInferenceError, match="positive finite consecutive durations"):
        engine_module._duration_normalized_rates(invalid_request, transitions)
    with pytest.raises(LongitudinalInferenceError, match="rate is non-finite"):
        engine_module._duration_normalized_rates(
            rate_request,
            (math.inf, *transitions[1:]),
        )


def test_pelt_segment_guards_and_heteroscedastic_cost() -> None:
    values = (0.0, 0.1, 5.0)
    low_error = (0.1, 0.1, 0.1)
    high_error = (0.1, 0.1, 2.0)
    assert heteroscedastic_huber_segment_cost(values, high_error, 0, 3) < (
        heteroscedastic_huber_segment_cost(values, low_error, 0, 3)
    )
    with pytest.raises(ValueError, match="segment bounds"):
        heteroscedastic_huber_segment_cost(values, low_error, 2, 2)
    with pytest.raises(ValueError, match="exact PELT"):
        exact_pelt_segmentation((0.0, 1.0), (1.0, 1.0), 1.0)
    with pytest.raises(ValueError, match="brute-force"):
        brute_force_segmentation(values, high_error, 0.0)


def test_demo_oracle_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        engine_module,
        "EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST",
        "sha256:" + "0" * 64,
    )
    with pytest.raises(SourceProfileIntegrityError, match="demo semantic oracle"):
        infer_longitudinal_gbm(synthetic_demo_request())


def test_private_numeric_guards_and_degenerate_statistics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    catalog = longitudinal_gbm_catalog()
    active = engine_module._active_pairs(request, 0, catalog)
    selected = engine_module._selected_replicates(catalog, "sha256:" + "1" * 64, 1)

    assert engine_module._effective_sample_size((0.0, 0.0)) == 0.0
    assert engine_module._quantile((2.5,), 0.05) == 2.5
    assert engine_module._sample_standard_deviation((2.5,)) == 0.0
    assert engine_module._sample_covariance((2.5,), (9.0,)) == 0.0
    assert engine_module._sample_covariance((1.0, 2.0), (2.0, 4.0)) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="equal length"):
        engine_module._sample_covariance((1.0,), ())
    assert (
        engine_module._project(
            np.asarray([], dtype=np.float64),
            (),
            {},
            (),
            (),
            (),
        )[0]
        is None
    )

    with pytest.raises(LongitudinalInferenceError, match="non-finite derived"):
        engine_module._project(
            np.asarray([math.inf], dtype=np.float64),
            active[:1],
            {active[0].feature.index: 0},
            (active[0].feature.index,),
            (1.0,),
            (active[0].feature.transition_scale,),
        )

    monkeypatch.setattr(engine_module, "_sample_reported_log_value", lambda *_: math.inf)
    with pytest.raises(LongitudinalInferenceError, match="non-finite log2 delta"):
        engine_module._draw_delta_evidence(active[:1], "sha256:" + "2" * 64, selected)


def _deadline_after(checkpoints: int) -> tuple[CancellationContext, dict[str, int]]:
    state = {"calls": 0}

    def clock() -> float:
        state["calls"] += 1
        return float(state["calls"])

    return CancellationContext(deadline=float(checkpoints), clock=clock), state


def test_expensive_bootstrap_projection_and_ablation_loops_cancel_cooperatively(
    demo_result,
) -> None:
    request = synthetic_demo_request()
    catalog = longitudinal_gbm_catalog()
    active = engine_module._active_pairs(request, 0, catalog)
    selected = engine_module._selected_replicates(catalog, "sha256:" + "4" * 64, 4)

    draw_context, draw_state = _deadline_after(4)
    with pytest.raises(InferenceDeadlineExceededError):
        engine_module._draw_delta_evidence(
            active[:2],
            "sha256:" + "5" * 64,
            selected,
            cancellation=draw_context,
        )
    assert draw_state["calls"] == 4

    projection_context, _ = _deadline_after(2)
    projection_pairs = active[:64]
    with pytest.raises(InferenceDeadlineExceededError):
        engine_module._project(
            np.asarray(
                [pair.expected_raw_delta for pair in projection_pairs],
                dtype=np.float64,
            ),
            projection_pairs,
            {pair.feature.index: index for index, pair in enumerate(projection_pairs)},
            tuple(pair.feature.index for pair in projection_pairs),
            tuple(pair.feature.ensemble_mean_coefficient for pair in projection_pairs),
            tuple(pair.feature.transition_scale for pair in projection_pairs),
            cancellation=projection_context,
        )

    raw_draws = np.zeros((2, len(active)), dtype=np.float64)
    work = engine_module._TransitionWork(
        evidence=demo_result.transitions[0],
        combined_slots=(0.0, 0.0),
        active_pairs=active,
        column_by_feature_index={pair.feature.index: index for index, pair in enumerate(active)},
        raw_delta_draws=raw_draws,
        selected_replicates=selected[:2],
    )
    source_context, _ = _deadline_after(2)
    with pytest.raises(InferenceDeadlineExceededError):
        engine_module._source_processing_ablation(
            work,
            0.0,
            AnalysisSupport.LIMITED,
            catalog,
            cancellation=source_context,
        )
    driver_context, _ = _deadline_after(2)
    with pytest.raises(InferenceDeadlineExceededError):
        engine_module._driver_ablations(
            work,
            demo_result.transitions[0].top_drivers[:1],
            0.0,
            AnalysisSupport.LIMITED,
            catalog,
            cancellation=driver_context,
        )


def test_segment_cost_and_pelt_dynamic_program_cancel_inside_loops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = (0.0, 0.0, 2.0, 2.0, -1.0, -1.0)
    errors = (0.1,) * len(values)
    segment_context, _ = _deadline_after(2)
    with pytest.raises(InferenceDeadlineExceededError):
        heteroscedastic_huber_segment_cost(
            values,
            errors,
            0,
            len(values),
            cancellation=segment_context,
        )

    monkeypatch.setattr(
        engine_module,
        "heteroscedastic_huber_segment_cost",
        lambda values, errors, start, end, **kwargs: 0.0,
    )
    pelt_context, state = _deadline_after(13)
    with pytest.raises(InferenceDeadlineExceededError):
        exact_pelt_segmentation(
            values,
            errors,
            3.0,
            cancellation=pelt_context,
        )
    assert state["calls"] == 13


def test_active_pair_filtering_and_driver_degenerate_paths() -> None:
    request = synthetic_demo_request()
    catalog = longitudinal_gbm_catalog()
    first = request.time_points[0]
    second = request.time_points[1]

    inactive = first.observations[1].model_copy(
        update={
            "state": ProteinEvidenceState.MISSING,
            "log_abundance": None,
            "standard_error": None,
            "quality_weight": 0.0,
        }
    )
    inactive_request = request.model_copy(
        update={
            "time_points": (
                first.model_copy(update={"observations": (first.observations[0], inactive)}),
                second.model_copy(update={"observations": second.observations[:2]}),
            )
        }
    )
    assert not engine_module._active_pairs(inactive_request, 0, catalog)

    relevant = catalog.ensemble_feature_indices | frozenset(
        catalog.source_processing_sensitivity.feature_indices
    )
    irrelevant = next(feature for feature in catalog.features if feature.index not in relevant)
    irrelevant_observations = tuple(
        point.observations[1].model_copy(update={"gene_symbol": irrelevant.gene_symbol})
        for point in request.time_points[:2]
    )
    irrelevant_request = request.model_copy(
        update={
            "time_points": tuple(
                point.model_copy(update={"observations": (observation,)})
                for point, observation in zip(
                    request.time_points[:2], irrelevant_observations, strict=True
                )
            )
        }
    )
    assert not engine_module._active_pairs(irrelevant_request, 0, catalog)

    pair = engine_module._active_pairs(request, 0, catalog)[0]
    zero_feature = replace(
        pair.feature,
        ensemble_mean_coefficient=0.0,
        ensemble_mean_absolute_coefficient=0.0,
    )
    zero_pair = replace(pair, feature=zero_feature)
    assert engine_module._drivers((zero_pair,), 0.0) == ()

    positive_pair = replace(
        pair,
        feature=replace(
            pair.feature,
            ensemble_mean_coefficient=0.5,
            ensemble_mean_absolute_coefficient=0.5,
        ),
        value_semantics="exact_delta",
    )
    lower_pair = replace(
        pair,
        feature=replace(
            pair.feature,
            index=irrelevant.index,
            gene_symbol=irrelevant.gene_symbol,
            source_gene_label=irrelevant.source_gene_label,
            ensemble_mean_coefficient=-0.5,
            ensemble_mean_absolute_coefficient=0.5,
        ),
        value_semantics="upper_bound",
        expected_raw_delta=-pair.feature.transition_scale,
    )
    drivers = engine_module._drivers((zero_pair, positive_pair, lower_pair), 0.0)
    assert drivers
    assert any(driver.value_semantics == "upper_bound" for driver in drivers)


def test_ablation_abstention_and_incomplete_pairing_paths(
    monkeypatch: pytest.MonkeyPatch,
    demo_result,
) -> None:
    assert (
        engine_module._ablation_estimate(
            (0.1,),
            primary_score=0.1,
            base_support=AnalysisSupport.SUPPORTED,
            expected_count=1,
        )[0]
        is AnalysisSupport.ABSTAINED
    )
    support, _, _, _, reason = engine_module._ablation_estimate(
        (0.1,) * 32,
        primary_score=0.2,
        base_support=AnalysisSupport.LIMITED,
        expected_count=33,
    )
    assert support is AnalysisSupport.LIMITED
    assert reason is not None and "primary transition" in reason and "some paired" in reason
    support, _, _, _, reason = engine_module._ablation_estimate(
        (0.1,) * 64,
        primary_score=0.2,
        base_support=AnalysisSupport.SUPPORTED,
        expected_count=64,
    )
    assert support is AnalysisSupport.SUPPORTED
    assert reason is None

    empty_work = engine_module._TransitionWork(
        evidence=demo_result.transitions[0],
        combined_slots=(),
        active_pairs=(),
        column_by_feature_index={},
        raw_delta_draws=None,
        selected_replicates=(),
    )
    catalog = longitudinal_gbm_catalog()
    assert (
        engine_module._source_processing_ablation(
            empty_work, 0.0, AnalysisSupport.SUPPORTED, catalog
        ).support
        is AnalysisSupport.ABSTAINED
    )
    assert (
        engine_module._driver_ablations(
            empty_work,
            demo_result.transitions[0].top_drivers[:1],
            0.0,
            AnalysisSupport.SUPPORTED,
            catalog,
        )
        == ()
    )

    active = engine_module._active_pairs(synthetic_demo_request(), 0, catalog)
    one_row = np.zeros((1, len(active)), dtype=np.float64)
    one_replicate = catalog.bootstrap_replicates[:1]
    incomplete_work = engine_module._TransitionWork(
        evidence=demo_result.transitions[0],
        combined_slots=(None,),
        active_pairs=active,
        column_by_feature_index={pair.feature.index: i for i, pair in enumerate(active)},
        raw_delta_draws=one_row,
        selected_replicates=one_replicate,
    )
    monkeypatch.setattr(engine_module, "_project", lambda *args, **kwargs: (None, 0.0, 0, 0.0))
    assert (
        engine_module._source_processing_ablation(
            incomplete_work, 0.0, AnalysisSupport.SUPPORTED, catalog
        ).support
        is AnalysisSupport.ABSTAINED
    )
    ablations = engine_module._driver_ablations(
        incomplete_work,
        demo_result.transitions[0].top_drivers[:1],
        0.0,
        AnalysisSupport.SUPPORTED,
        catalog,
    )
    assert ablations[0].support is AnalysisSupport.ABSTAINED


@pytest.mark.parametrize("mode", ["abstained", "estimable"])
def test_transition_projection_loss_and_limited_support_paths(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    estimable = mode == "estimable"
    request = synthetic_demo_request().model_copy(update={"bootstrap_replicates": 33})
    catalog = longitudinal_gbm_catalog()
    active = engine_module._active_pairs(request, 0, catalog)
    selected = catalog.bootstrap_replicates[:33]
    monkeypatch.setattr(engine_module, "_active_pairs", lambda *args: active)
    monkeypatch.setattr(engine_module, "_support_metrics", lambda *args: (10, 0.20, 5.0, 0.5))
    monkeypatch.setattr(engine_module, "_selected_replicates", lambda *args: selected)
    monkeypatch.setattr(
        engine_module,
        "_draw_delta_evidence",
        lambda *args, **kwargs: np.zeros((33, len(active)), dtype=np.float64),
    )
    calls = 0

    def projection(*_args, **_kwargs):
        nonlocal calls
        current = calls
        calls += 1
        if not estimable or current == 0:
            return None, 0.2, 10, 5.0
        return 0.1, 0.2, 10, 5.0

    monkeypatch.setattr(engine_module, "_project", projection)
    monkeypatch.setattr(engine_module, "_drivers", lambda *args: ())
    work = engine_module._calculate_transition(
        request,
        0,
        catalog,
        request.request_digest,
        "sha256:" + "3" * 64,
        cancellation=None,
    )
    if estimable:
        assert work.evidence.support is AnalysisSupport.LIMITED
        assert len(work.evidence.abstention_reasons) == 5
        assert "fewer than 64" in work.evidence.abstention_reasons[-1]
        assert work.evidence.bootstrap_replicates_used == 32
    else:
        assert work.evidence.support is AnalysisSupport.ABSTAINED
        assert work.evidence.bootstrap_replicates_used == 0


def test_transition_with_64_complete_projections_can_be_fully_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request().model_copy(update={"bootstrap_replicates": 64})
    catalog = longitudinal_gbm_catalog()
    active = engine_module._active_pairs(request, 0, catalog)
    selected = catalog.bootstrap_replicates[:64]
    monkeypatch.setattr(engine_module, "_active_pairs", lambda *args: active)
    monkeypatch.setattr(engine_module, "_support_metrics", lambda *args: (64, 0.50, 32.0, 0.5))
    monkeypatch.setattr(engine_module, "_selected_replicates", lambda *args: selected)
    monkeypatch.setattr(
        engine_module,
        "_draw_delta_evidence",
        lambda *args, **kwargs: np.zeros((64, len(active)), dtype=np.float64),
    )
    monkeypatch.setattr(engine_module, "_project", lambda *args, **kwargs: (0.1, 0.5, 64, 32.0))
    monkeypatch.setattr(engine_module, "_drivers", lambda *args: ())

    work = engine_module._calculate_transition(
        request,
        0,
        catalog,
        request.request_digest,
        "sha256:" + "3" * 64,
        cancellation=None,
    )
    assert work.evidence.support is AnalysisSupport.SUPPORTED
    assert work.evidence.bootstrap_replicates_used == 64
    assert work.evidence.abstention_reasons == ()


def test_pelt_defensive_oracles_and_nonestimable_joint_paths(
    monkeypatch: pytest.MonkeyPatch,
    demo_result,
) -> None:
    with pytest.raises(ValueError, match="finite with positive errors"):
        heteroscedastic_huber_segment_cost((0.0, math.inf, 1.0), (1.0,) * 3, 0, 3)

    incumbent = engine_module._Partition(1.0, (2,))
    assert engine_module._prefer_partition(engine_module._Partition(1.0, (1,)), incumbent)
    assert not engine_module._prefer_partition(engine_module._Partition(1.0, (3,)), incumbent)

    monkeypatch.setattr(
        engine_module,
        "heteroscedastic_huber_segment_cost",
        lambda values, errors, start, end, **kwargs: 0.0 if end - start > 2 else 1.0,
    )
    with pytest.raises(ValueError, match="K=0 condition"):
        exact_pelt_segmentation((0.0, 1.0, 2.0, 3.0), (1.0,) * 4, 1.0)
    monkeypatch.undo()

    request = synthetic_demo_request()
    two_point_request = request.model_copy(update={"time_points": request.time_points[:2]})
    empty_work = engine_module._TransitionWork(
        evidence=demo_result.transitions[0],
        combined_slots=(),
        active_pairs=(),
        column_by_feature_index={},
        raw_delta_draws=None,
        selected_replicates=(),
    )
    assert engine_module._pelt_analysis(two_point_request, (empty_work,), cancellation=None) is None

    four_point_request = request.model_copy(update={"time_points": request.time_points[:4]})
    no_joint = engine_module._pelt_analysis(
        four_point_request, (empty_work, empty_work, empty_work), cancellation=None
    )
    assert no_joint is not None and no_joint.support is AnalysisSupport.ABSTAINED
    no_pelt = demo_result.model_copy(update={"pelt_analysis": None})
    assert engine_module.semantic_result_projection(no_pelt)["pelt_analysis"] is None


def test_rate_pelt_receipt_boundaries_support_and_partial_joint_paths(demo_result) -> None:
    request = synthetic_demo_request()
    template = request.time_points[0]
    points = tuple(
        template.model_copy(
            update={"time_point_id": f"seg.{index}", "time_offset_days": 90.0 * index}
        )
        for index in range(7)
    )
    rate_request = request.model_copy(update={"bootstrap_replicates": 64, "time_points": points})
    rate_values = (0.0, 0.0, 4.0, 4.0, -2.0, -2.0)
    works = tuple(
        engine_module._TransitionWork(
            evidence=demo_result.transitions[0].model_copy(
                update={"support": AnalysisSupport.SUPPORTED, "score": rate}
            ),
            combined_slots=(rate,) * 64,
            active_pairs=(),
            column_by_feature_index={},
            raw_delta_draws=None,
            selected_replicates=(),
        )
        for rate in rate_values
    )

    analysis = engine_module._pelt_analysis(rate_request, works, cancellation=None)
    assert analysis is not None
    assert analysis.support is AnalysisSupport.SUPPORTED
    assert analysis.reason is None
    assert tuple(boundary.boundary_index for boundary in analysis.boundaries) == (2, 4)
    assert tuple(
        (boundary.left_time_point_id, boundary.right_time_point_id)
        for boundary in analysis.boundaries
    ) == (("seg.1", "seg.2"), ("seg.3", "seg.4"))
    assert all(boundary.bootstrap_frequency == 1.0 for boundary in analysis.boundaries)
    assert all(boundary.cost_reduction > 0.0 for boundary in analysis.boundaries)

    partial_first = replace(works[0], combined_slots=(*works[0].combined_slots[:-1], None))
    partial = engine_module._pelt_analysis(
        rate_request,
        (partial_first, *works[1:]),
        cancellation=None,
    )
    assert partial is not None and partial.support is AnalysisSupport.LIMITED
    assert partial.bootstrap_replicates_used == 63
    assert partial.reason == (
        "some joint transition bootstrap paths were not estimable; "
        "fewer than 64 joint bootstrap rate paths for full support"
    )

    abstained_first = replace(
        works[0],
        evidence=works[0].evidence.model_copy(update={"support": AnalysisSupport.ABSTAINED}),
    )
    abstained = engine_module._pelt_analysis(
        rate_request,
        (abstained_first, *works[1:]),
        cancellation=None,
    )
    assert abstained is not None and abstained.support is AnalysisSupport.ABSTAINED
    assert abstained.reason == "at least one consecutive transition is not estimable"

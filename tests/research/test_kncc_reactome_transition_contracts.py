from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.research.longitudinal_gbm_reactome_transition.canonical import (
    computational_request_digest,
    normalized_request,
    result_payload_digest,
    sha256_digest,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.catalog import (
    reactome_transition_source_catalog,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    AnalysisSupport,
    ConditionalComponentAblation,
    ConditionalPathwayAblations,
    ConditionalProteinContribution,
    ConditionalTransitionClassification,
    ConditionalUncertaintyDecomposition,
    ContributionDirection,
    GlobalRecurrenceClassification,
    GlobalRecurrenceConcordance,
    LongitudinalGbmReactomeTransitionRequest,
    LongitudinalGbmReactomeTransitionResult,
    ReactomeConditionalEvaluationSummary,
    ReactomeConditionalReplayVerificationRequest,
    ReactomeConditionalReplayVerificationResult,
    ReactomeConditionalTransitionEvidence,
    ReactomePathwayConcordance,
    ReactomeTransitionProvenance,
    UncertaintyState,
    UnverifiedLongitudinalGbmReactomeTransitionResult,
    ValueSemantics,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.demo import (
    DEMO_ID,
    synthetic_demo_request,
)

DIGEST = "sha256:" + "1" * 64
OTHER_DIGEST = "sha256:" + "2" * 64
LIMITATIONS = (
    "Conditional concordance is not pathway activation or flux.",
    "Reactome membership is annotation rather than causal direction.",
    "The model has same-cohort patient-grouped evaluation only.",
    "No recurrence risk, prognosis, or treatment response is inferred.",
    "Missing and unsupported evidence remain absent.",
    "Outputs are research-use-only and non-prescriptive.",
)


def estimated_uncertainty() -> ConditionalUncertaintyDecomposition:
    return ConditionalUncertaintyDecomposition(
        state=UncertaintyState.ESTIMATED,
        measurement_standard_error=0.08,
        fitted_model_standard_error=0.06,
        measurement_model_covariance=0.001,
        combined_standard_error=0.11,
        variance_closure_residual=0.0,
        bootstrap_replicates_used=64,
    )


def not_estimable_uncertainty() -> ConditionalUncertaintyDecomposition:
    return ConditionalUncertaintyDecomposition(
        state=UncertaintyState.NOT_ESTIMABLE,
        reason="insufficient evidence",
    )


def ablation(
    *,
    support: AnalysisSupport = AnalysisSupport.SUPPORTED,
    kind: str = "global_axis",
    score: float = 0.02,
) -> ConditionalComponentAblation:
    if support is AnalysisSupport.ABSTAINED:
        return ConditionalComponentAblation(
            component_kind=kind,
            component_id="global",
            support=support,
            classification_without_component=(
                ConditionalTransitionClassification.NOT_ESTIMABLE
            ),
            removed_feature_count=16,
            reason="not estimable",
        )
    return ConditionalComponentAblation(
        component_kind=kind,
        component_id="global",
        support=support,
        conditional_score_without_component=score,
        score_delta=0.01,
        classification_without_component=(
            ConditionalTransitionClassification.CONDITIONALLY_STABLE
        ),
        removed_feature_count=16,
        reason="direction sensitive" if support is AnalysisSupport.LIMITED else None,
    )


def contribution() -> ConditionalProteinContribution:
    return ConditionalProteinContribution(
        gene_symbol="EGFR",
        from_observation_id="from.egfr",
        to_observation_id="to.egfr",
        from_provenance_digest=DIGEST,
        to_provenance_digest=DIGEST,
        from_state="observed",
        to_state="observed",
        value_semantics=ValueSemantics.EXACT_DELTA,
        standardized_delta=0.5,
        pathway_loading=0.4,
        global_loading=0.1,
        unadjusted_contribution=0.20,
        global_adjustment_contribution=0.05,
        conditional_contribution=0.15,
        direction=ContributionDirection.CONDITIONAL_SOURCE_RECURRENCE_ALIGNED,
        reliability_weight=0.9,
    )


def evaluation_summary() -> ReactomeConditionalEvaluationSummary:
    return ReactomeConditionalEvaluationSummary(
        protocol=(
            "eight deterministic held-patient folds with all source statistics and "
            "loadings refit; five deterministic held-gene folds within each held patient"
        ),
        validation_scope="same-cohort reconstruction; not external validation",
        interpretation=(
            "the joint dictionary has a modest collective reconstruction advantage; "
            "individual pathway attribution is not established by cohort-level removal"
        ),
        zero_prediction_median_standardized_mae=0.7108931329,
        global_only_median_standardized_mae=0.5622984198,
        joint_median_standardized_mae=0.5554163035,
        median_relative_mae_improvement=0.0120459348,
        evaluation_improved_fraction=0.6653846154,
        patient_cluster_median_improvement=0.0129728555,
        patient_cluster_median_improvement_90_interval=(0.0085182357, 0.0178616382),
        reference_design_condition_number=5.2021989549,
        outer_design_condition_minimum=5.1651525999,
        outer_design_condition_maximum=5.3525550754,
        minimum_outer_loading_cosine=0.9851914172,
        leave_pathway_out_nonconverged_count=0,
    )


def global_concordance(
    *,
    support: AnalysisSupport = AnalysisSupport.SUPPORTED,
) -> GlobalRecurrenceConcordance:
    if support is AnalysisSupport.ABSTAINED:
        return GlobalRecurrenceConcordance(
            support=support,
            classification=GlobalRecurrenceClassification.NOT_ESTIMABLE,
            shared_active_gene_count=0,
            coefficient_mass_coverage=0.0,
            effective_sample_size=0.0,
            bootstrap_replicates_used=0,
            abstention_reasons=("insufficient evidence",),
        )
    return GlobalRecurrenceConcordance(
        support=support,
        classification=GlobalRecurrenceClassification.STABLE,
        score=0.02,
        lower_bound=-0.10,
        upper_bound=0.15,
        shared_active_gene_count=32,
        coefficient_mass_coverage=0.75,
        effective_sample_size=20.0,
        bootstrap_replicates_used=64,
        abstention_reasons=("sensitivity",) if support is AnalysisSupport.LIMITED else (),
    )


def pathway(
    index: int,
    *,
    support: AnalysisSupport | None = None,
) -> ReactomePathwayConcordance:
    source = reactome_transition_source_catalog().pathways[index]
    overlap = source.reactome_id == "R-HSA-198203"
    selected_support = support or (
        AnalysisSupport.LIMITED if overlap else AnalysisSupport.SUPPORTED
    )
    if selected_support is AnalysisSupport.ABSTAINED:
        return ReactomePathwayConcordance(
            panel_index=index,
            domain_id=source.domain_id,
            reactome_id=source.reactome_id,
            pathway_name=source.name,
            support=selected_support,
            classification=ConditionalTransitionClassification.NOT_ESTIMABLE,
            source_member_count=source.source_member_count,
            mapped_feature_count=source.mapped_feature_count,
            fitted_feature_count=max(1, source.eligible_feature_count),
            active_feature_count=0,
            observed_count=0,
            left_censored_count=0,
            coefficient_mass_coverage=0.0,
            unique_active_gene_count=0,
            unique_coefficient_mass=0.0,
            effective_sample_size=0.0,
            overlap_confounded=overlap,
            uncertainty=not_estimable_uncertainty(),
            ablations=ConditionalPathwayAblations(),
            abstention_reasons=("insufficient evidence",),
        )
    reasons = ("overlap-confounded conditional coordinate",) if overlap else ()
    unique_ablation_support = (
        AnalysisSupport.ABSTAINED if overlap else AnalysisSupport.SUPPORTED
    )
    return ReactomePathwayConcordance(
        panel_index=index,
        domain_id=source.domain_id,
        reactome_id=source.reactome_id,
        pathway_name=source.name,
        support=selected_support,
        classification=ConditionalTransitionClassification.CONDITIONALLY_STABLE,
        score=0.03,
        lower_bound=-0.10,
        upper_bound=0.15,
        unadjusted_pathway_coordinate=0.08,
        global_adjustment=0.05,
        source_member_count=source.source_member_count,
        mapped_feature_count=source.mapped_feature_count,
        fitted_feature_count=source.eligible_feature_count,
        active_feature_count=max(5, source.eligible_feature_count),
        observed_count=max(4, source.eligible_feature_count - 1),
        left_censored_count=1,
        coefficient_mass_coverage=0.8,
        unique_active_gene_count=0 if overlap else 4,
        unique_coefficient_mass=0.0 if overlap else 0.3,
        effective_sample_size=4.0,
        request_reconstruction_evaluable_fold_count=5,
        request_reconstruction_improved_fold_count=4,
        request_reconstruction_median_relative_gain=0.02,
        stability=0.8,
        discordance=0.1,
        overlap_confounded=overlap,
        uncertainty=estimated_uncertainty(),
        top_contributions=(contribution(),),
        ablations=ConditionalPathwayAblations(
            global_axis=ablation(),
            source_processing=(ablation(kind="source_processing"),),
            degree_normalization=ablation(kind="degree_normalization"),
            unique_members=ablation(
                kind="unique_members",
                support=unique_ablation_support,
            ),
            leave_pathway_out=ablation(kind="leave_pathway_out"),
        ),
        abstention_reasons=reasons,
    )


def transition(
    request: LongitudinalGbmReactomeTransitionRequest,
    index: int = 0,
) -> ReactomeConditionalTransitionEvidence:
    return ReactomeConditionalTransitionEvidence(
        transition_id=f"transition.{index}",
        transition_index=index,
        from_time_point_id=request.time_points[index].time_point_id,
        to_time_point_id=request.time_points[index + 1].time_point_id,
        duration_days=(
            request.time_points[index + 1].time_offset_days
            - request.time_points[index].time_offset_days
        ),
        global_recurrence=global_concordance(),
        pathways=tuple(pathway(i) for i in range(10)),
    )


def test_supported_stable_pathway_accepts_an_exact_zero_coordinate() -> None:
    stable = pathway(0).model_copy(
        update={
            "score": 0.0,
            "unadjusted_pathway_coordinate": 0.05,
            "global_adjustment": 0.05,
        }
    )

    assert ReactomePathwayConcordance.model_validate(stable, strict=True).score == 0.0


def provenance(
    request: LongitudinalGbmReactomeTransitionRequest,
    *,
    profile_digest: str = DIGEST,
) -> ReactomeTransitionProvenance:
    return ReactomeTransitionProvenance(
        request_digest=request.request_digest,
        profile_digest=profile_digest,
        computational_digest=DIGEST,
        numerical_seed_digest=DIGEST,
        source_catalog_artifact_digest=DIGEST,
        source_catalog_content_digest=DIGEST,
        source_binding_digest=DIGEST,
        selection_candidate_digest=DIGEST,
        pathway_order_digest=DIGEST,
        pathway_membership_digest=DIGEST,
        gene_order_digest=DIGEST,
        patient_order_rule_digest=DIGEST,
        fitted_artifact_digest=DIGEST,
        fitted_content_digest=DIGEST,
        union_feature_digest=DIGEST,
        reference_tensor_digest=DIGEST,
        centering_scaling_digest=DIGEST,
        reference_design_digest=DIGEST,
        global_loading_digest=DIGEST,
        conditional_loading_digest=DIGEST,
        bootstrap_ensemble_digest=DIGEST,
        training_recipe_digest=DIGEST,
        fold_policy_digest=DIGEST,
        source_processing_ablation_digest=DIGEST,
        evaluation_digest=DIGEST,
        input_contract_schema_digest=DIGEST,
        engine_semantic_digest=DIGEST,
        demo_semantic_oracle_digest=DIGEST,
        assay_compatibility_digest=sha256_digest(
            request.assay_compatibility.model_dump(mode="json")
        ),
        normalization_reference_digest=request.normalization_reference.binding_digest,
        caller_evidence_set_digest=DIGEST,
        numpy_version="2.5.2",
        bootstrap_seed=7,
        source_attribution="Synthetic test source attribution.",
        source_licenses=("PDC CC-BY-4.0", "Reactome CC0-1.0"),
        source_transformation_notice="No patient identifiers or values are redistributed.",
    )


def result_document(
    request: LongitudinalGbmReactomeTransitionRequest | None = None,
    *,
    profile_digest: str = DIGEST,
) -> dict[str, Any]:
    typed_request = request or synthetic_demo_request()
    document: dict[str, Any] = {
        "profile_digest": profile_digest,
        "request_digest": typed_request.request_digest,
        "result_digest": DIGEST,
        "series_id": typed_request.series_id,
        "assay_compatibility": typed_request.assay_compatibility,
        "normalization_reference": typed_request.normalization_reference,
        "time_point_ids": tuple(point.time_point_id for point in typed_request.time_points),
        "transitions": tuple(
            transition(typed_request, index)
            for index in range(len(typed_request.time_points) - 1)
        ),
        "provenance": provenance(typed_request, profile_digest=profile_digest),
        "limitations": LIMITATIONS,
    }
    unverified = UnverifiedLongitudinalGbmReactomeTransitionResult.model_validate(
        document,
        strict=True,
    )
    typed_document = unverified.model_dump(mode="python")
    typed_document["result_digest"] = result_payload_digest(unverified)
    return typed_document


def result(
    request: LongitudinalGbmReactomeTransitionRequest | None = None,
) -> LongitudinalGbmReactomeTransitionResult:
    return LongitudinalGbmReactomeTransitionResult.model_validate(
        result_document(request),
        strict=True,
    )


def mutate(model: object, **updates: object) -> dict[str, Any]:
    document = model.model_dump(mode="python")  # type: ignore[attr-defined]
    document.update(updates)
    return document


def test_demo_request_is_strict_bounded_and_input_order_invariant() -> None:
    request = synthetic_demo_request()
    assert request.series_id == DEMO_ID
    assert request.bootstrap_replicates == 64
    assert len(request.time_points) == 4
    assert len(request.time_points[0].observations) == 1_692
    reordered = request.model_dump(mode="python")
    reordered["time_points"][0]["observations"] = tuple(
        reversed(reordered["time_points"][0]["observations"])
    )
    parsed = LongitudinalGbmReactomeTransitionRequest.model_validate(reordered, strict=True)
    assert parsed.request_digest == request.request_digest
    assert normalized_request(parsed) == normalized_request(request)
    numerical = computational_request_digest(request, profile_digest=DIGEST)
    alternate = request.model_copy(update={"series_id": "alternate.receipt"})
    assert alternate.request_digest != request.request_digest
    assert computational_request_digest(alternate, profile_digest=DIGEST) == numerical


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_points", "time-point identifiers"),
        ("unordered", "strictly increasing"),
        ("reference", "invariant request normalization"),
        ("duplicate_observations", "unique across the series"),
    ],
)
def test_request_rejects_cross_series_inconsistency(mutation: str, message: str) -> None:
    document = synthetic_demo_request().model_dump(mode="python")
    if mutation == "duplicate_points":
        document["time_points"][1]["time_point_id"] = document["time_points"][0][
            "time_point_id"
        ]
    elif mutation == "unordered":
        document["time_points"][1]["time_offset_days"] = 0.0
    elif mutation == "reference":
        document["time_points"][1]["normalization_reference_digest"] = OTHER_DIGEST
    else:
        document["time_points"][1]["observations"][0]["observation_id"] = document[
            "time_points"
        ][0]["observations"][0]["observation_id"]
    with pytest.raises(ValidationError, match=message):
        LongitudinalGbmReactomeTransitionRequest.model_validate(document, strict=True)


def test_uncertainty_contract_enforces_closed_state() -> None:
    assert estimated_uncertainty().state is UncertaintyState.ESTIMATED
    assert not_estimable_uncertainty().reason
    estimated = estimated_uncertainty().model_dump(mode="python")
    for update, message in (
        ({"measurement_standard_error": None}, "every component"),
        ({"bootstrap_replicates_used": 0}, "every component"),
        ({"reason": "bad"}, "cannot carry a reason"),
    ):
        with pytest.raises(ValidationError, match=message):
            ConditionalUncertaintyDecomposition.model_validate(
                {**estimated, **update}, strict=True
            )


def test_evaluation_summary_exposes_modest_same_cohort_evidence_bounds() -> None:
    valid = evaluation_summary()
    assert valid.patient_count == 104
    assert valid.all_primary_solver_fits_converged
    assert valid.all_leave_pathway_q05_q95_intervals_cross_zero
    cases = (
        (
            {"joint_median_standardized_mae": 0.8},
            "median MAE ordering",
        ),
        (
            {"patient_cluster_median_improvement_90_interval": (0.014, 0.02)},
            "patient-cluster improvement interval",
        ),
        (
            {"reference_design_condition_number": 6.0},
            "held-fold condition bounds",
        ),
    )
    for update, message in cases:
        with pytest.raises(ValidationError, match=message):
            ReactomeConditionalEvaluationSummary.model_validate(
                mutate(valid, **update),
                strict=True,
            )
    abstained = not_estimable_uncertainty().model_dump(mode="python")
    for update, message in (
        ({"combined_standard_error": 0.1}, "cannot carry statistics"),
        ({"bootstrap_replicates_used": 1}, "reason and zero"),
        ({"reason": None}, "reason and zero"),
    ):
        with pytest.raises(ValidationError, match=message):
            ConditionalUncertaintyDecomposition.model_validate(
                {**abstained, **update}, strict=True
            )


def test_contribution_enforces_exact_observed_decomposition_and_direction() -> None:
    valid = contribution()
    assert valid.conditional_contribution == pytest.approx(0.15)
    for update, message in (
        ({"conditional_contribution": 0.14}, "does not close"),
        ({"conditional_contribution": 0.0, "unadjusted_contribution": 0.05}, "zero"),
        (
            {"direction": ContributionDirection.CONDITIONAL_SOURCE_PRIMARY_ALIGNED},
            "does not match",
        ),
    ):
        with pytest.raises(ValidationError, match=message):
            ConditionalProteinContribution.model_validate(mutate(valid, **update), strict=True)
    for field in ("from_state", "to_state"):
        with pytest.raises(ValidationError):
            ConditionalProteinContribution.model_validate(
                mutate(valid, **{field: "left_censored"}), strict=True
            )


def test_ablation_contract_enforces_support_state() -> None:
    assert ablation().reason is None
    assert ablation(support=AnalysisSupport.LIMITED).reason
    assert ablation(support=AnalysisSupport.ABSTAINED).reason
    supported = ablation().model_dump(mode="python")
    abstained = ablation(support=AnalysisSupport.ABSTAINED).model_dump(mode="python")
    cases = (
        ({**abstained, "score_delta": 1.0}, "cannot carry numeric"),
        (
            {
                **abstained,
                "classification_without_component": (
                    ConditionalTransitionClassification.INDETERMINATE
                ),
            },
            "must be not_estimable",
        ),
        ({**abstained, "reason": None}, "require a reason"),
        ({**supported, "score_delta": None}, "require score"),
        (
            {
                **supported,
                "classification_without_component": (
                    ConditionalTransitionClassification.NOT_ESTIMABLE
                ),
            },
            "cannot be not_estimable",
        ),
        ({**supported, "reason": "bad"}, "cannot carry"),
        ({**supported, "support": AnalysisSupport.LIMITED}, "require a limitation"),
    )
    for document, message in cases:
        with pytest.raises(ValidationError, match=message):
            ConditionalComponentAblation.model_validate(document, strict=True)


@pytest.mark.parametrize(
    ("lower", "upper", "classification"),
    [
        (0.26, 0.5, GlobalRecurrenceClassification.SOURCE_RECURRENCE_ALIGNED),
        (-0.5, -0.26, GlobalRecurrenceClassification.SOURCE_PRIMARY_ALIGNED),
        (-0.25, 0.25, GlobalRecurrenceClassification.STABLE),
        (-0.3, 0.3, GlobalRecurrenceClassification.INDETERMINATE),
    ],
)
def test_global_interval_only_classification(
    lower: float,
    upper: float,
    classification: GlobalRecurrenceClassification,
) -> None:
    document = global_concordance().model_dump(mode="python")
    document.update(score=(lower + upper) / 2.0, lower_bound=lower, upper_bound=upper)
    document["classification"] = classification
    assert GlobalRecurrenceConcordance.model_validate(document, strict=True).classification is (
        classification
    )


def test_global_support_contract_rejects_mixed_states_and_below_gates() -> None:
    valid = global_concordance().model_dump(mode="python")
    abstained = global_concordance(support=AnalysisSupport.ABSTAINED).model_dump(mode="python")
    cases = (
        ({**abstained, "score": 0.0}, "cannot carry estimates"),
        (
            {**abstained, "classification": GlobalRecurrenceClassification.INDETERMINATE},
            "must be not_estimable",
        ),
        ({**abstained, "abstention_reasons": ()}, "requires reasons"),
        ({**valid, "upper_bound": None}, "complete interval"),
        ({**valid, "score": 0.5}, "must contain"),
        (
            {
                **valid,
                "classification": GlobalRecurrenceClassification.INDETERMINATE,
            },
            "supported by its interval",
        ),
        ({**valid, "shared_active_gene_count": 15}, "support gates"),
        ({**valid, "coefficient_mass_coverage": 0.24}, "support gates"),
        ({**valid, "effective_sample_size": 7.9}, "support gates"),
        ({**valid, "bootstrap_replicates_used": 0}, "requires bootstraps"),
        ({**valid, "abstention_reasons": ("bad",)}, "cannot carry limitation"),
        ({**valid, "support": AnalysisSupport.LIMITED}, "requires a limitation"),
    )
    for document, message in cases:
        with pytest.raises(ValidationError, match=message):
            GlobalRecurrenceConcordance.model_validate(document, strict=True)


def test_pathway_contract_allows_numeric_limited_pi3k_but_not_supported_pi3k() -> None:
    pi3k = pathway(2)
    assert pi3k.support is AnalysisSupport.LIMITED
    assert pi3k.score is not None
    assert pi3k.overlap_confounded is True
    assert pi3k.unique_active_gene_count == 0
    with pytest.raises(ValidationError, match="cannot be supported"):
        ReactomePathwayConcordance.model_validate(
            mutate(pi3k, support=AnalysisSupport.SUPPORTED, abstention_reasons=()),
            strict=True,
        )
    with pytest.raises(ValidationError, match="always overlap-confounded"):
        ReactomePathwayConcordance.model_validate(
            mutate(pi3k, overlap_confounded=False), strict=True
        )


@pytest.mark.parametrize(
    ("lower", "upper", "classification"),
    [
        (
            0.26,
            0.5,
            ConditionalTransitionClassification.CONDITIONAL_SOURCE_RECURRENCE_ALIGNED,
        ),
        (
            -0.5,
            -0.26,
            ConditionalTransitionClassification.CONDITIONAL_SOURCE_PRIMARY_ALIGNED,
        ),
        (-0.25, 0.25, ConditionalTransitionClassification.CONDITIONALLY_STABLE),
        (-0.3, 0.3, ConditionalTransitionClassification.INDETERMINATE),
    ],
)
def test_pathway_interval_only_classification(
    lower: float,
    upper: float,
    classification: ConditionalTransitionClassification,
) -> None:
    document = pathway(0).model_dump(mode="python")
    document.update(score=(lower + upper) / 2.0, lower_bound=lower, upper_bound=upper)
    document["classification"] = classification
    document["support"] = AnalysisSupport.LIMITED
    document["abstention_reasons"] = ("interval classification test",)
    parsed = ReactomePathwayConcordance.model_validate(document, strict=True)
    assert parsed.classification is classification


def test_pathway_contract_rejects_identity_count_support_and_explanation_mixtures() -> None:
    valid_pathway = pathway(0)
    valid = valid_pathway.model_dump(mode="python")
    valid_ablations = valid_pathway.ablations
    abstained = pathway(0, support=AnalysisSupport.ABSTAINED).model_dump(mode="python")
    cases = (
        ({**valid, "domain_id": "wrong"}, "locked Reactome panel"),
        ({**valid, "observed_count": valid["observed_count"] - 1}, "active pathway count"),
        (
            {**valid, "unique_active_gene_count": valid["active_feature_count"] + 1},
            "cannot exceed",
        ),
        ({**abstained, "score": 0.0}, "cannot carry estimates"),
        (
            {
                **abstained,
                "classification": ConditionalTransitionClassification.INDETERMINATE,
            },
            "must be not_estimable",
        ),
        ({**abstained, "stability": 0.0}, "cannot carry diagnostics"),
        ({**abstained, "uncertainty": estimated_uncertainty()}, "must be non-estimable"),
        ({**abstained, "top_contributions": (contribution(),)}, "cannot carry explanations"),
        (
            {**abstained, "request_reconstruction_improved_fold_count": 1},
            "request reconstruction evidence",
        ),
        ({**abstained, "abstention_reasons": ()}, "requires a reason"),
        ({**valid, "global_adjustment": None}, "requires every coordinate"),
        ({**valid, "score": 0.5}, "must contain"),
        (
            {
                **valid,
                "classification": ConditionalTransitionClassification.INDETERMINATE,
            },
            "supported by its interval",
        ),
        ({**valid, "active_feature_count": 4, "observed_count": 3}, "support gates"),
        ({**valid, "coefficient_mass_coverage": 0.49}, "support gates"),
        ({**valid, "effective_sample_size": 2.9}, "support gates"),
        ({**valid, "stability": None}, "uncertainty and explanations"),
        (
            {**valid, "uncertainty": not_estimable_uncertainty()},
            "uncertainty and explanations",
        ),
        (
            {**valid, "ablations": ConditionalPathwayAblations()},
            "uncertainty and explanations",
        ),
        ({**valid, "abstention_reasons": ("bad",)}, "cannot carry limitation"),
        ({**valid, "unique_active_gene_count": 2}, "unique attribution"),
        ({**valid, "unique_coefficient_mass": 0.19}, "unique attribution"),
        ({**valid, "support": AnalysisSupport.LIMITED}, "requires a limitation"),
        (
            {**valid, "request_reconstruction_improved_fold_count": 3},
            "cross-gene reconstruction gain",
        ),
        (
            {**valid, "request_reconstruction_median_relative_gain": 0.009},
            "cross-gene reconstruction gain",
        ),
        ({**valid, "stability": 0.79}, "stable classified bootstrap"),
        (
            {
                **valid,
                "uncertainty": estimated_uncertainty().model_copy(
                    update={"bootstrap_replicates_used": 32}
                ),
            },
            "stable classified bootstrap",
        ),
        (
            {
                **valid,
                "classification": ConditionalTransitionClassification.INDETERMINATE,
                "lower_bound": -0.3,
                "upper_bound": 0.3,
            },
            "stable classified bootstrap",
        ),
        (
            {
                **valid,
                "ablations": valid_ablations.model_copy(
                    update={
                        "unique_members": ablation(
                            kind="unique_members",
                            support=AnalysisSupport.ABSTAINED,
                        )
                    }
                ),
            },
            "estimable unique-members",
        ),
        (
            {
                **valid,
                "ablations": valid_ablations.model_copy(
                    update={
                        "leave_pathway_out": ablation(
                            kind="leave_pathway_out",
                            support=AnalysisSupport.ABSTAINED,
                        )
                    }
                ),
            },
            "available leave-pathway-out",
        ),
        (
            {
                **valid,
                "ablations": valid_ablations.model_copy(
                    update={
                        "degree_normalization": ablation(
                            kind="degree_normalization",
                            score=-0.02,
                        )
                    }
                ),
            },
            "reverse direction",
        ),
    )
    for document, message in cases:
        with pytest.raises(ValidationError, match=message):
            ReactomePathwayConcordance.model_validate(document, strict=True)


def test_transition_requires_all_ten_pathways_in_order_and_global_estimability() -> None:
    request = synthetic_demo_request()
    valid = transition(request)
    reversed_family = tuple(reversed(valid.pathways))
    with pytest.raises(ValidationError, match="complete fixed pathway order"):
        ReactomeConditionalTransitionEvidence.model_validate(
            mutate(valid, pathways=reversed_family), strict=True
        )
    with pytest.raises(ValidationError, match="must abstain"):
        ReactomeConditionalTransitionEvidence.model_validate(
            mutate(valid, global_recurrence=global_concordance(support=AnalysisSupport.ABSTAINED)),
            strict=True,
        )


def test_result_is_content_bound_and_replay_union_accepts_unverified_receipt() -> None:
    request = synthetic_demo_request()
    verified = result(request)
    assert verified.result_digest == result_payload_digest(verified)
    forged_document = result_document(request)
    forged_document["result_digest"] = OTHER_DIGEST
    with pytest.raises(ValidationError, match="canonical result content"):
        LongitudinalGbmReactomeTransitionResult.model_validate(
            forged_document, strict=True
        )
    unverified = UnverifiedLongitudinalGbmReactomeTransitionResult.model_validate(
        forged_document, strict=True
    )
    envelope = ReactomeConditionalReplayVerificationRequest(
        request=request,
        result=unverified,
    )
    assert envelope.result.result_digest == OTHER_DIGEST


def test_replay_summary_contract_rejects_contradictory_flags() -> None:
    valid = {
        "verified": True,
        "request_digest_match": True,
        "profile_digest_match": True,
        "result_digest_match": True,
        "transition_topology_match": True,
        "global_recurrence_semantic_match": True,
        "pathway_semantic_match": True,
        "uncertainty_semantic_match": True,
        "ablation_semantic_match": True,
        "provenance_match": True,
        "document_semantic_match": True,
        "semantic_match": True,
        "recomputed_request_digest": DIGEST,
        "recomputed_result_digest": DIGEST,
        "message": "exact replay",
    }
    assert ReactomeConditionalReplayVerificationResult.model_validate(
        valid,
        strict=True,
    ).verified
    with pytest.raises(ValidationError, match="semantic replay summary"):
        ReactomeConditionalReplayVerificationResult.model_validate(
            {**valid, "document_semantic_match": False},
            strict=True,
        )
    with pytest.raises(ValidationError, match="verification summary"):
        ReactomeConditionalReplayVerificationResult.model_validate(
            {**valid, "verified": False},
            strict=True,
        )


def test_result_rejects_provenance_and_transition_topology_mismatch() -> None:
    request = synthetic_demo_request()
    valid = result_document(request)
    cases = []
    wrong_profile = deepcopy(valid)
    wrong_profile["profile_digest"] = OTHER_DIGEST
    cases.append((wrong_profile, "profile digest"))
    wrong_request = deepcopy(valid)
    wrong_request["request_digest"] = OTHER_DIGEST
    cases.append((wrong_request, "request digest"))
    wrong_assay = deepcopy(valid)
    wrong_assay["provenance"]["assay_compatibility_digest"] = OTHER_DIGEST
    cases.append((wrong_assay, "assay compatibility digest"))
    wrong_normalization = deepcopy(valid)
    wrong_normalization["provenance"]["normalization_reference_digest"] = OTHER_DIGEST
    cases.append((wrong_normalization, "normalization reference"))
    duplicate_points = deepcopy(valid)
    duplicate_points["time_point_ids"] = (
        duplicate_points["time_point_ids"][0],
    ) * len(duplicate_points["time_point_ids"])
    cases.append((duplicate_points, "time-point identifiers"))
    missing_transition = deepcopy(valid)
    missing_transition["transitions"] = missing_transition["transitions"][:-1]
    cases.append((missing_transition, "one transition"))
    duplicate_transition = deepcopy(valid)
    duplicate_transition["transitions"][1]["transition_id"] = duplicate_transition[
        "transitions"
    ][0]["transition_id"]
    cases.append((duplicate_transition, "transition identifiers"))
    wrong_index = deepcopy(valid)
    wrong_index["transitions"][1]["transition_index"] = 0
    cases.append((wrong_index, "consecutive and zero-based"))
    wrong_endpoint = deepcopy(valid)
    wrong_endpoint["transitions"][0]["to_time_point_id"] = request.time_points[2].time_point_id
    cases.append((wrong_endpoint, "endpoints"))
    for document, message in cases:
        document["result_digest"] = result_payload_digest(document)
        with pytest.raises(ValidationError, match=message):
            LongitudinalGbmReactomeTransitionResult.model_validate(document, strict=True)

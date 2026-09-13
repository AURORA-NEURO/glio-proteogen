from __future__ import annotations

from typing import cast

import pytest

from glio_proteogen.research.longitudinal_gbm_neftel_transition import contracts
from glio_proteogen.research.longitudinal_gbm_neftel_transition.contracts import (
    AnalysisSupport,
    ConditionalComponentAblation,
    ConditionalProgramAblations,
    ConditionalTransitionClassification,
    ConditionalUncertaintyDecomposition,
    ContributionDirection,
    GlobalTransitionClassification,
    LongitudinalGbmNeftelTransitionRequest,
    LongitudinalGbmNeftelTransitionResult,
    NeftelProgramReplayVerificationRequest,
    NeftelProgramReplayVerificationResult,
    ProteinEvidenceState,
    UncertaintyState,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.demo import (
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.profile import (
    algorithm_profile,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.service import (
    analyze_longitudinal_gbm_neftel_transition,
    verify_longitudinal_gbm_neftel_transition_replay,
)

DIGEST = "sha256:" + "1" * 64


@pytest.fixture(scope="module")
def demo_request() -> LongitudinalGbmNeftelTransitionRequest:
    source = synthetic_demo_request()
    return source.model_copy(
        update={"time_points": source.time_points[:2], "bootstrap_replicates": 32}
    )


@pytest.fixture(scope="module")
def result(
    demo_request: LongitudinalGbmNeftelTransitionRequest,
) -> LongitudinalGbmNeftelTransitionResult:
    return analyze_longitudinal_gbm_neftel_transition(demo_request)


def _assert_validator_error(value: object, method: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        getattr(value, method)()


def test_request_validator_defensive_branches(
    demo_request: LongitudinalGbmNeftelTransitionRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = demo_request.time_points
    duplicate_time = second.model_copy(update={"time_point_id": first.time_point_id})
    _assert_validator_error(
        demo_request.model_copy(update={"time_points": (first, duplicate_time)}),
        "series_is_ordered_unique_and_reference_bound",
        "identifiers must be unique",
    )
    unordered = second.model_copy(update={"time_offset_days": first.time_offset_days})
    _assert_validator_error(
        demo_request.model_copy(update={"time_points": (first, unordered)}),
        "series_is_ordered_unique_and_reference_bound",
        "strictly increasing",
    )
    wrong_reference = second.model_copy(update={"normalization_reference_digest": DIGEST})
    _assert_validator_error(
        demo_request.model_copy(update={"time_points": (first, wrong_reference)}),
        "series_is_ordered_unique_and_reference_bound",
        "invariant request normalization",
    )
    duplicate_observation = second.observations[0].model_copy(
        update={"observation_id": first.observations[0].observation_id}
    )
    duplicate_observations = second.model_copy(
        update={"observations": (duplicate_observation, *second.observations[1:])}
    )
    _assert_validator_error(
        demo_request.model_copy(update={"time_points": (first, duplicate_observations)}),
        "series_is_ordered_unique_and_reference_bound",
        "observation identifiers",
    )
    monkeypatch.setattr(contracts, "MAX_TOTAL_OBSERVATIONS", 1)
    _assert_validator_error(
        demo_request,
        "series_is_ordered_unique_and_reference_bound",
        "limited to",
    )
    monkeypatch.setattr(contracts, "MAX_TOTAL_OBSERVATIONS", 12_000)
    monkeypatch.setattr(contracts, "MAX_SOLVER_WORK_UNITS", 1)
    _assert_validator_error(
        demo_request,
        "series_is_ordered_unique_and_reference_bound",
        "solver-work-unit",
    )


def test_uncertainty_validator_defensive_branches(
    result: LongitudinalGbmNeftelTransitionResult,
) -> None:
    uncertainty = result.transitions[0].programs[0].uncertainty
    _assert_validator_error(
        uncertainty.model_copy(update={"measurement_standard_error": None}),
        "statistics_match_state",
        "requires every component",
    )
    _assert_validator_error(
        uncertainty.model_copy(update={"reason": "forged"}),
        "statistics_match_state",
        "cannot carry a reason",
    )
    non_estimable = ConditionalUncertaintyDecomposition(
        state=UncertaintyState.NOT_ESTIMABLE,
        reason="not estimable",
    )
    _assert_validator_error(
        non_estimable.model_copy(update={"combined_standard_error": 0.1}),
        "statistics_match_state",
        "cannot carry statistics",
    )
    _assert_validator_error(
        non_estimable.model_copy(update={"reason": None}),
        "statistics_match_state",
        "requires a reason",
    )


def test_contribution_and_classification_defensive_branches(
    result: LongitudinalGbmNeftelTransitionResult,
) -> None:
    contribution = next(
        item for program in result.transitions[0].programs for item in program.top_contributions
    )
    _assert_validator_error(
        contribution.model_copy(update={"conditional_contribution": 0.12345678}),
        "direction_and_decomposition_are_consistent",
        "does not close",
    )
    zero = contribution.model_copy(
        update={
            "unadjusted_contribution": contribution.global_adjustment_contribution,
            "conditional_contribution": 0.0,
        }
    )
    _assert_validator_error(
        zero,
        "direction_and_decomposition_are_consistent",
        "zero contributions",
    )
    wrong_direction = (
        ContributionDirection.CONDITIONAL_SOURCE_EARLIER_TIMEPOINT_ALIGNED
        if contribution.conditional_contribution > 0.0
        else ContributionDirection.CONDITIONAL_SOURCE_LATER_TIMEPOINT_ALIGNED
    )
    _assert_validator_error(
        contribution.model_copy(update={"direction": wrong_direction}),
        "direction_and_decomposition_are_consistent",
        "direction does not match",
    )
    assert contracts._expected_global_classification(0.26, 0.4) is (
        GlobalTransitionClassification.SOURCE_LATER_TIMEPOINT_ALIGNED
    )
    assert contracts._expected_global_classification(-0.4, -0.26) is (
        GlobalTransitionClassification.SOURCE_EARLIER_TIMEPOINT_ALIGNED
    )
    assert contracts._expected_global_classification(-0.25, 0.25) is (
        GlobalTransitionClassification.STABLE
    )
    assert contracts._expected_global_classification(-0.4, 0.4) is (
        GlobalTransitionClassification.INDETERMINATE
    )
    assert contracts._expected_program_classification(0.26, 0.4) is (
        ConditionalTransitionClassification.CONDITIONAL_SOURCE_LATER_TIMEPOINT_ALIGNED
    )
    assert contracts._expected_program_classification(-0.4, -0.26) is (
        ConditionalTransitionClassification.CONDITIONAL_SOURCE_EARLIER_TIMEPOINT_ALIGNED
    )
    assert contracts._expected_program_classification(-0.25, 0.25) is (
        ConditionalTransitionClassification.CONDITIONALLY_STABLE
    )
    assert contracts._expected_program_classification(-0.4, 0.4) is (
        ConditionalTransitionClassification.INDETERMINATE
    )


def test_ablation_validator_defensive_branches(
    result: LongitudinalGbmNeftelTransitionResult,
) -> None:
    numeric = cast(
        "ConditionalComponentAblation",
        result.transitions[0].programs[0].ablations.global_axis,
    )
    abstained = ConditionalComponentAblation(
        component_kind="global_axis",
        component_id="global",
        support=AnalysisSupport.ABSTAINED,
        classification_without_component=ConditionalTransitionClassification.NOT_ESTIMABLE,
        removed_feature_count=0,
        reason="not estimable",
    )
    _assert_validator_error(
        abstained.model_copy(update={"conditional_score_without_component": 0.0}),
        "estimate_matches_support",
        "cannot carry numeric",
    )
    _assert_validator_error(
        abstained.model_copy(
            update={
                "classification_without_component": (
                    ConditionalTransitionClassification.CONDITIONALLY_STABLE
                )
            }
        ),
        "estimate_matches_support",
        "must be not_estimable",
    )
    _assert_validator_error(
        abstained.model_copy(update={"reason": None}),
        "estimate_matches_support",
        "require a reason",
    )
    _assert_validator_error(
        numeric.model_copy(update={"conditional_score_without_component": None}),
        "estimate_matches_support",
        "require score",
    )
    _assert_validator_error(
        numeric.model_copy(
            update={
                "classification_without_component": (
                    ConditionalTransitionClassification.NOT_ESTIMABLE
                )
            }
        ),
        "estimate_matches_support",
        "cannot be not_estimable",
    )
    _assert_validator_error(
        numeric.model_copy(update={"support": AnalysisSupport.SUPPORTED}),
        "estimate_matches_support",
        "cannot carry a limitation",
    )
    _assert_validator_error(
        numeric.model_copy(update={"reason": None}),
        "estimate_matches_support",
        "require a limitation",
    )
    assert not ConditionalProgramAblations().has_any()
    assert ConditionalProgramAblations().required_structural() is None
    assert result.transitions[0].programs[0].ablations.has_any()
    assert result.transitions[0].programs[0].ablations.required_structural() is not None


def test_global_validator_defensive_branches(
    result: LongitudinalGbmNeftelTransitionResult,
) -> None:
    global_result = result.transitions[0].global_transition
    abstained = global_result.model_copy(
        update={
            "support": AnalysisSupport.ABSTAINED,
            "classification": GlobalTransitionClassification.NOT_ESTIMABLE,
            "score": None,
            "lower_bound": None,
            "upper_bound": None,
            "bootstrap_replicates_used": 0,
            "abstention_reasons": ("not estimable",),
        }
    )
    _assert_validator_error(
        abstained.model_copy(update={"score": 0.0}),
        "interpretation_matches_support",
        "cannot carry estimates",
    )
    _assert_validator_error(
        abstained.model_copy(update={"classification": GlobalTransitionClassification.STABLE}),
        "interpretation_matches_support",
        "must be not_estimable",
    )
    _assert_validator_error(
        abstained.model_copy(update={"abstention_reasons": ()}),
        "interpretation_matches_support",
        "requires reasons",
    )
    _assert_validator_error(
        global_result.model_copy(update={"support": AnalysisSupport.SUPPORTED}),
        "interpretation_matches_support",
        "capped at limited",
    )
    _assert_validator_error(
        global_result.model_copy(update={"score": None}),
        "interpretation_matches_support",
        "complete interval",
    )
    _assert_validator_error(
        global_result.model_copy(update={"lower_bound": cast("float", global_result.score) + 1}),
        "interpretation_matches_support",
        "must contain",
    )
    _assert_validator_error(
        global_result.model_copy(
            update={"classification": GlobalTransitionClassification.SOURCE_LATER_TIMEPOINT_ALIGNED}
        ),
        "interpretation_matches_support",
        "classification must be supported",
    )
    _assert_validator_error(
        global_result.model_copy(
            update={
                "admitted_active_gene_count": 0,
                "shared_active_gene_count": 0,
                "observed_count": 0,
                "left_censored_count": 0,
                "admitted_left_censored_count": 0,
            }
        ),
        "interpretation_matches_support",
        "support gates",
    )
    _assert_validator_error(
        global_result.model_copy(update={"shared_active_gene_count": 0}),
        "interpretation_matches_support",
        "informative global count",
    )
    _assert_validator_error(
        global_result.model_copy(update={"admitted_active_gene_count": 0}),
        "interpretation_matches_support",
        "admitted global count",
    )
    _assert_validator_error(
        global_result.model_copy(
            update={
                "admitted_active_gene_count": 1,
                "shared_active_gene_count": 2,
                "observed_count": 1,
                "left_censored_count": 1,
                "admitted_left_censored_count": 0,
            }
        ),
        "interpretation_matches_support",
        "cannot exceed admitted",
    )
    _assert_validator_error(
        global_result.model_copy(update={"bootstrap_replicates_used": 0}),
        "interpretation_matches_support",
        "requires bootstraps",
    )
    _assert_validator_error(
        global_result.model_copy(update={"abstention_reasons": ()}),
        "interpretation_matches_support",
        "requires a limitation",
    )


def test_program_validator_defensive_branches(
    result: LongitudinalGbmNeftelTransitionResult,
) -> None:
    program = result.transitions[0].programs[0]
    not_estimable = ConditionalUncertaintyDecomposition(
        state=UncertaintyState.NOT_ESTIMABLE,
        reason="not estimable",
    )
    abstained = program.model_copy(
        update={
            "support": AnalysisSupport.ABSTAINED,
            "classification": ConditionalTransitionClassification.NOT_ESTIMABLE,
            "score": None,
            "lower_bound": None,
            "upper_bound": None,
            "unadjusted_program_coordinate": None,
            "global_adjustment": None,
            "request_reconstruction_evaluable_fold_count": 0,
            "request_reconstruction_improved_fold_count": 0,
            "request_reconstruction_median_relative_gain": None,
            "stability": None,
            "discordance": None,
            "uncertainty": not_estimable,
            "top_contributions": (),
            "ablations": ConditionalProgramAblations(),
            "abstention_reasons": ("not estimable",),
        }
    )
    _assert_validator_error(
        program.model_copy(update={"domain_id": "forged"}),
        "interpretation_matches_support_and_panel",
        "identity",
    )
    _assert_validator_error(
        program.model_copy(update={"active_feature_count": 0}),
        "interpretation_matches_support_and_panel",
        "informative program count",
    )
    _assert_validator_error(
        program.model_copy(update={"admitted_active_feature_count": 0}),
        "interpretation_matches_support_and_panel",
        "admitted program count",
    )
    _assert_validator_error(
        program.model_copy(
            update={
                "admitted_active_feature_count": 1,
                "active_feature_count": 2,
                "observed_count": 1,
                "left_censored_count": 1,
                "admitted_left_censored_count": 0,
            }
        ),
        "interpretation_matches_support_and_panel",
        "cannot exceed admitted",
    )
    _assert_validator_error(
        program.model_copy(update={"unique_active_gene_count": program.active_feature_count + 1}),
        "interpretation_matches_support_and_panel",
        "unique active genes",
    )
    _assert_validator_error(
        program.model_copy(
            update={
                "request_reconstruction_evaluable_fold_count": 0,
                "request_reconstruction_improved_fold_count": 1,
            }
        ),
        "interpretation_matches_support_and_panel",
        "improved request reconstruction",
    )
    abstained_cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"score": 0.0}, "cannot carry estimates"),
        (
            {"classification": ConditionalTransitionClassification.CONDITIONALLY_STABLE},
            "must be not_estimable",
        ),
        ({"stability": 0.5}, "cannot carry diagnostics"),
        ({"uncertainty": program.uncertainty}, "must be non-estimable"),
        (
            {"request_reconstruction_evaluable_fold_count": 1},
            "reconstruction evidence",
        ),
        ({"top_contributions": program.top_contributions}, "cannot carry explanations"),
        ({"abstention_reasons": ()}, "requires a reason"),
    )
    for update, match in abstained_cases:
        _assert_validator_error(
            abstained.model_copy(update=update),
            "interpretation_matches_support_and_panel",
            match,
        )
    estimated_cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"score": None}, "requires every coordinate"),
        ({"lower_bound": cast("float", program.score) + 1.0}, "must contain"),
        (
            {
                "classification": (
                    ConditionalTransitionClassification.CONDITIONAL_SOURCE_LATER_TIMEPOINT_ALIGNED
                )
            },
            "classification must be supported",
        ),
        (
            {
                "active_feature_count": 4,
                "admitted_active_feature_count": 4,
                "unique_active_gene_count": 4,
                "observed_count": 4,
                "left_censored_count": 0,
                "admitted_left_censored_count": 0,
            },
            "support gates",
        ),
        ({"ablations": ConditionalProgramAblations()}, "requires uncertainty"),
        ({"support": AnalysisSupport.SUPPORTED}, "cannot be supported"),
        ({"abstention_reasons": ()}, "requires a limitation"),
    )
    for update, match in estimated_cases:
        _assert_validator_error(
            program.model_copy(update=update),
            "interpretation_matches_support_and_panel",
            match,
        )


def test_transition_result_replay_and_profile_defensive_branches(
    demo_request: LongitudinalGbmNeftelTransitionRequest,
    result: LongitudinalGbmNeftelTransitionResult,
) -> None:
    transition = result.transitions[0]
    _assert_validator_error(
        transition.model_copy(update={"programs": tuple(reversed(transition.programs))}),
        "program_family_is_complete_and_ordered",
        "complete fixed program order",
    )
    abstained_global = transition.global_transition.model_copy(
        update={
            "support": AnalysisSupport.ABSTAINED,
            "classification": GlobalTransitionClassification.NOT_ESTIMABLE,
            "score": None,
            "lower_bound": None,
            "upper_bound": None,
            "bootstrap_replicates_used": 0,
            "abstention_reasons": ("not estimable",),
        }
    )
    _assert_validator_error(
        transition.model_copy(update={"global_transition": abstained_global}),
        "program_family_is_complete_and_ordered",
        "programs must abstain",
    )

    provenance = result.provenance
    provenance_cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"profile_digest": DIGEST}, "profile digest"),
        ({"request_digest": DIGEST}, "request digest"),
    )
    for update, match in provenance_cases:
        _assert_validator_error(
            result.model_copy(update=update),
            "topology_and_provenance_are_consistent",
            match,
        )
    _assert_validator_error(
        result.model_copy(
            update={
                "provenance": provenance.model_copy(update={"assay_compatibility_digest": DIGEST})
            }
        ),
        "topology_and_provenance_are_consistent",
        "assay compatibility",
    )
    _assert_validator_error(
        result.model_copy(
            update={
                "provenance": provenance.model_copy(
                    update={"normalization_reference_digest": DIGEST}
                )
            }
        ),
        "topology_and_provenance_are_consistent",
        "normalization reference",
    )
    _assert_validator_error(
        result.model_copy(update={"time_point_ids": ("same", "same")}),
        "topology_and_provenance_are_consistent",
        "time-point identifiers",
    )
    _assert_validator_error(
        result.model_copy(update={"transitions": ()}),
        "topology_and_provenance_are_consistent",
        "one transition",
    )
    duplicate_transition = transition.model_copy(update={"transition_index": 1})
    _assert_validator_error(
        result.model_copy(
            update={
                "time_point_ids": ("a", "b", "c"),
                "transitions": (transition, transition),
            }
        ),
        "topology_and_provenance_are_consistent",
        "transition identifiers",
    )
    _assert_validator_error(
        result.model_copy(update={"transitions": (duplicate_transition,)}),
        "topology_and_provenance_are_consistent",
        "indices must be consecutive",
    )
    _assert_validator_error(
        result.model_copy(
            update={
                "transitions": (transition.model_copy(update={"from_time_point_id": "forged"}),)
            }
        ),
        "topology_and_provenance_are_consistent",
        "endpoints",
    )
    _assert_validator_error(
        result.model_copy(update={"result_digest": DIGEST}),
        "result_is_content_bound",
        "canonical result content",
    )

    verification = verify_longitudinal_gbm_neftel_transition_replay(
        NeftelProgramReplayVerificationRequest(request=demo_request, result=result)
    )
    _assert_validator_error(
        verification.model_copy(update={"semantic_match": False}),
        "verification_summary_matches_components",
        "semantic replay summary",
    )
    _assert_validator_error(
        verification.model_copy(update={"verified": False}),
        "verification_summary_matches_components",
        "verification summary",
    )

    profile = algorithm_profile()
    evaluation = profile.evaluation
    evaluation_cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"equal_membership_median_standardized_mae": 0.9}, "MAE ordering"),
        (
            {"patient_cluster_joint_vs_global_median_gain_90_interval": (-0.1, 0.1)},
            "joint-vs-global interval",
        ),
        (
            {"patient_cluster_joint_vs_equal_median_gain_90_interval": (-0.2, 0.1)},
            "joint-vs-equal interval",
        ),
        ({"reference_design_condition_number": 1.0}, "reference condition"),
        (
            {"equal_membership_reference_design_condition_number": 2.0},
            "equal-membership condition",
        ),
    )
    for update, match in evaluation_cases:
        _assert_validator_error(
            evaluation.model_copy(update=update),
            "metrics_expose_only_the_locked_modest_evidence",
            match,
        )
    profile_program = profile.programs[0]
    _assert_validator_error(
        profile_program.model_copy(update={"domain_id": "forged"}),
        "identity_matches_catalog",
        "identity",
    )
    _assert_validator_error(
        profile_program.model_copy(update={"fitted_feature_count": 500}),
        "identity_matches_catalog",
        "nested within mapped",
    )
    _assert_validator_error(
        profile.model_copy(update={"programs": tuple(reversed(profile.programs))}),
        "profile_is_complete_ordered_and_content_bound",
        "complete fixed program order",
    )
    _assert_validator_error(
        profile.model_copy(update={"profile_digest": DIGEST}),
        "profile_is_complete_ordered_and_content_bound",
        "canonical profile content",
    )


def test_replay_summary_valid_false_case() -> None:
    value = NeftelProgramReplayVerificationResult(
        verified=False,
        request_digest_match=False,
        profile_digest_match=True,
        result_digest_match=True,
        transition_topology_match=True,
        global_transition_semantic_match=True,
        program_semantic_match=True,
        uncertainty_semantic_match=True,
        ablation_semantic_match=True,
        provenance_match=True,
        document_semantic_match=True,
        semantic_match=True,
        recomputed_request_digest=DIGEST,
        recomputed_result_digest=DIGEST,
        message="not verified",
    )
    assert not value.verified
    assert ProteinEvidenceState.MISSING.value == "missing"

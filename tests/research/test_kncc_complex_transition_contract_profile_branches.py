from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from glio_proteogen.research.longitudinal_gbm.contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    LongitudinalTimePoint,
    NormalizationReference,
    ProteinEvidenceState,
    ProteinObservation,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition import (
    profile as profile_module,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.contracts import (
    AnalysisSupport,
    ComplexComponentAblation,
    ComplexMemberContribution,
    ComplexMemberTransitionConcordance,
    ComplexTransitionAblations,
    ComplexTransitionClassification,
    ComplexTransitionEvidence,
    ComplexTransitionProvenance,
    ComplexTransitionReplayVerificationResult,
    ComplexTransitionUncertainty,
    ContributionDirection,
    LongitudinalGbmComplexTransitionProfile,
    LongitudinalGbmComplexTransitionRequest,
    UncertaintyState,
    UnverifiedLongitudinalGbmComplexTransitionResult,
    ValueSemantics,
)

_DIGEST = "sha256:" + "1" * 64
_OTHER_DIGEST = "sha256:" + "2" * 64
_PROFILE_DIGEST = "sha256:" + "3" * 64


def _observation(point: int) -> ProteinObservation:
    return ProteinObservation(
        observation_id=f"branch.observation.{point}",
        gene_symbol="EGFR",
        state=ProteinEvidenceState.OBSERVED,
        log_abundance=1.0 + point,
        standard_error=0.1,
        quality_weight=0.9,
        provenance_digest=_DIGEST,
    )


def _request() -> LongitudinalGbmComplexTransitionRequest:
    reference = NormalizationReference(
        reference_id="branch.reference",
        binding_digest=_DIGEST,
        normalization_method="locked test reference",
    )
    return LongitudinalGbmComplexTransitionRequest(
        series_id="branch.series",
        assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        normalization_reference=reference,
        time_points=tuple(
            LongitudinalTimePoint(
                time_point_id=f"branch.time.{point}",
                time_offset_days=float(point * 30),
                normalization_reference_digest=_DIGEST,
                observations=(_observation(point),),
            )
            for point in range(2)
        ),
        bootstrap_replicates=32,
    )


def _estimated_uncertainty() -> ComplexTransitionUncertainty:
    return ComplexTransitionUncertainty(
        state=UncertaintyState.ESTIMATED,
        measurement_standard_error=0.1,
        fitted_model_standard_error=0.2,
        measurement_model_covariance=0.0,
        combined_standard_error=0.3,
        variance_closure_residual=0.0,
        bootstrap_replicates_used=32,
    )


def _not_estimable_uncertainty() -> ComplexTransitionUncertainty:
    return ComplexTransitionUncertainty(
        state=UncertaintyState.NOT_ESTIMABLE,
        reason="insufficient active members",
    )


def _estimated_ablation(component_kind: str) -> ComplexComponentAblation:
    return ComplexComponentAblation(
        component_kind=component_kind,
        component_id=f"branch.{component_kind}",
        support=AnalysisSupport.SUPPORTED,
        score_without_component=0.05,
        score_delta=0.05,
        classification_without_component=ComplexTransitionClassification.STABLE,
        removed_member_count=0,
    )


def _estimated_complex(
    *,
    index: int = 0,
    support: AnalysisSupport = AnalysisSupport.LIMITED,
) -> ComplexMemberTransitionConcordance:
    return ComplexMemberTransitionConcordance(
        complex_index=index,
        domain_id=f"branch.domain.{index}",
        reactome_id=f"R-HSA-{100 + index}",
        complex_name=f"Branch complex {index}",
        family_id=f"branch.family.{index}",
        support=support,
        classification=ComplexTransitionClassification.STABLE,
        score=0.05,
        lower_bound=-0.1,
        upper_bound=0.2,
        active_member_count=3,
        observed_member_count=3,
        left_censored_member_count=0,
        coefficient_mass_coverage=0.8,
        effective_sample_size=3.0,
        coherence=0.8,
        discordance=0.2,
        stability=0.9,
        solver_converged=True,
        solver_iterations=2,
        solver_initial_objective=1.0,
        solver_final_objective=0.5,
        solver_objective_monotone=True,
        least_source_aligned_observed_member="EGFR",
        source_held_member_relative_gain=0.2,
        source_panel_patient_cluster_gain_90_interval=(0.1, 0.3),
        source_direction_accuracy=0.75,
        source_minimum_outer_loading_cosine=0.9,
        uncertainty=_estimated_uncertainty(),
        ablations=ComplexTransitionAblations(
            source_processing=_estimated_ablation("source_processing"),
            uniform_member_loading=_estimated_ablation("uniform_member_loading"),
        ),
        limitations=("pilot support",) if support is AnalysisSupport.LIMITED else (),
    )


def _abstained_complex(*, index: int = 0) -> ComplexMemberTransitionConcordance:
    return ComplexMemberTransitionConcordance(
        complex_index=index,
        domain_id=f"branch.domain.{index}",
        reactome_id=f"R-HSA-{100 + index}",
        complex_name=f"Branch complex {index}",
        family_id=f"branch.family.{index}",
        support=AnalysisSupport.ABSTAINED,
        classification=ComplexTransitionClassification.NOT_ESTIMABLE,
        active_member_count=0,
        observed_member_count=0,
        left_censored_member_count=0,
        coefficient_mass_coverage=0.0,
        effective_sample_size=0.0,
        source_held_member_relative_gain=0.1,
        source_panel_patient_cluster_gain_90_interval=(-0.1, 0.2),
        source_direction_accuracy=0.5,
        source_minimum_outer_loading_cosine=0.9,
        uncertainty=_not_estimable_uncertainty(),
        ablations=ComplexTransitionAblations(),
        limitations=("insufficient active members",),
    )


def _transition() -> ComplexTransitionEvidence:
    return ComplexTransitionEvidence(
        transition_id="branch.transition.0",
        transition_index=0,
        from_time_point_id="branch.time.0",
        to_time_point_id="branch.time.1",
        duration_days=30.0,
        complexes=(_abstained_complex(),),
    )


def _unverified_result() -> UnverifiedLongitudinalGbmComplexTransitionResult:
    request = _request()
    return UnverifiedLongitudinalGbmComplexTransitionResult(
        request_digest=request.request_digest,
        result_digest=_OTHER_DIGEST,
        profile_digest=_PROFILE_DIGEST,
        source_catalog_digest=_DIGEST,
        fitted_model_digest=_OTHER_DIGEST,
        computational_seed=1,
        series_id=request.series_id,
        assay_compatibility=request.assay_compatibility,
        normalization_reference=request.normalization_reference,
        time_point_ids=tuple(point.time_point_id for point in request.time_points),
        transitions=(_transition(),),
        provenance=ComplexTransitionProvenance(
            source_study_id="PDC000514",
            source_patient_pair_count=104,
            reactome_release=97,
            source_catalog_digest=_DIGEST,
            fitted_model_digest=_OTHER_DIGEST,
            training_recipe_digest=_DIGEST,
            panel_selection_digest=_OTHER_DIGEST,
            participant_membership_digest=_DIGEST,
            source_licenses=("PDC source: CC-BY-4.0", "Reactome annotation: CC0-1.0"),
            source_attribution="Synthetic validator branch fixture.",
            validation_scope="internal_patient_grouped_held_member_reconstruction",
        ),
        limitations=("Participant-set concordance is not complex assembly.",),
    )


def test_request_cross_field_guards_reject_each_invalid_series_topology() -> None:
    base = _request().model_dump(mode="python")

    duplicate_point = deepcopy(base)
    duplicate_point["time_points"][1]["time_point_id"] = "branch.time.0"
    with pytest.raises(ValidationError, match="time-point identifiers must be unique"):
        LongitudinalGbmComplexTransitionRequest.model_validate(duplicate_point, strict=True)

    unordered = deepcopy(base)
    unordered["time_points"][1]["time_offset_days"] = 0.0
    with pytest.raises(ValidationError, match="time offsets must be strictly increasing"):
        LongitudinalGbmComplexTransitionRequest.model_validate(unordered, strict=True)

    foreign_reference = deepcopy(base)
    foreign_reference["time_points"][1]["normalization_reference_digest"] = _OTHER_DIGEST
    with pytest.raises(ValidationError, match="invariant request normalization/reference digest"):
        LongitudinalGbmComplexTransitionRequest.model_validate(foreign_reference, strict=True)

    duplicate_observation = deepcopy(base)
    duplicate_observation["time_points"][1]["observations"][0]["observation_id"] = (
        "branch.observation.0"
    )
    with pytest.raises(ValidationError, match="observation identifiers must be unique"):
        LongitudinalGbmComplexTransitionRequest.model_validate(duplicate_observation, strict=True)


def test_request_total_observation_guard_uses_the_flattened_series_count() -> None:
    request = _request()
    points = tuple(
        SimpleNamespace(
            time_point_id=f"branch.large.{point}",
            time_offset_days=float(point),
            normalization_reference_digest=_DIGEST,
            observations=tuple(
                SimpleNamespace(observation_id=f"branch.large.{point}.{index}")
                for index in range(6_001)
            ),
        )
        for point in range(2)
    )
    oversized = request.model_copy(update={"time_points": points})

    with pytest.raises(ValueError, match="limited to 12000 observations"):
        oversized.series_is_ordered_unique_and_reference_bound()


def test_uncertainty_state_rejects_every_cross_state_payload() -> None:
    with pytest.raises(ValidationError, match="requires all components"):
        ComplexTransitionUncertainty(state=UncertaintyState.ESTIMATED)

    estimated = _estimated_uncertainty().model_dump(mode="python")
    estimated["reason"] = "unexpected"
    with pytest.raises(ValidationError, match="estimated uncertainty cannot carry a reason"):
        ComplexTransitionUncertainty.model_validate(estimated, strict=True)

    with pytest.raises(ValidationError, match="cannot carry statistics"):
        ComplexTransitionUncertainty(
            state=UncertaintyState.NOT_ESTIMABLE,
            measurement_standard_error=0.1,
            reason="not estimable",
        )

    for payload in (
        {"state": UncertaintyState.NOT_ESTIMABLE},
        {
            "state": UncertaintyState.NOT_ESTIMABLE,
            "bootstrap_replicates_used": 1,
            "reason": "not estimable",
        },
    ):
        with pytest.raises(ValidationError, match="requires a reason and zero bootstraps"):
            ComplexTransitionUncertainty.model_validate(payload, strict=True)


def test_contribution_sign_and_direction_are_bound() -> None:
    base = {
        "gene_symbol": "EGFR",
        "from_observation_id": "branch.observation.0",
        "to_observation_id": "branch.observation.1",
        "from_provenance_digest": _DIGEST,
        "to_provenance_digest": _OTHER_DIGEST,
        "value_semantics": ValueSemantics.EXACT_DELTA,
        "standardized_delta": 0.5,
        "member_loading": 0.4,
        "reliability_weight": 0.9,
        "contribution": 0.2,
        "direction": ContributionDirection.SOURCE_RECURRENCE_ALIGNED,
    }
    assert ComplexMemberContribution.model_validate(base, strict=True).contribution == 0.2
    reverse = {
        **base,
        "contribution": -0.2,
        "direction": ContributionDirection.SOURCE_PRIMARY_ALIGNED,
    }
    assert ComplexMemberContribution.model_validate(reverse, strict=True).contribution == -0.2

    with pytest.raises(ValidationError, match="zero complex-member contributions"):
        ComplexMemberContribution.model_validate({**base, "contribution": 0.0}, strict=True)
    with pytest.raises(ValidationError, match="direction does not match its sign"):
        ComplexMemberContribution.model_validate(
            {**base, "direction": ContributionDirection.SOURCE_PRIMARY_ALIGNED},
            strict=True,
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {
                "support": AnalysisSupport.ABSTAINED,
                "classification_without_component": ComplexTransitionClassification.NOT_ESTIMABLE,
                "score_without_component": 0.1,
                "score_delta": None,
                "reason": "abstained",
            },
            "abstained ablations cannot carry estimates",
        ),
        (
            {
                "support": AnalysisSupport.ABSTAINED,
                "classification_without_component": ComplexTransitionClassification.STABLE,
                "score_without_component": None,
                "score_delta": None,
                "reason": "abstained",
            },
            "abstained ablations must be not_estimable",
        ),
        (
            {
                "support": AnalysisSupport.ABSTAINED,
                "classification_without_component": ComplexTransitionClassification.NOT_ESTIMABLE,
                "score_without_component": None,
                "score_delta": None,
                "reason": None,
            },
            "abstained ablations require a reason",
        ),
        (
            {"score_without_component": None, "score_delta": None},
            "estimated ablations require score and delta",
        ),
        (
            {"classification_without_component": ComplexTransitionClassification.NOT_ESTIMABLE},
            "estimated ablations cannot be not_estimable",
        ),
        ({"reason": "unexpected"}, "supported ablations cannot carry a reason"),
        (
            {"support": AnalysisSupport.LIMITED, "reason": None},
            "limited ablations require a reason",
        ),
    ],
)
def test_ablation_support_contract_rejects_incoherent_payloads(updates, message) -> None:
    base = _estimated_ablation("source_processing").model_dump(mode="python")
    base.update(updates)
    with pytest.raises(ValidationError, match=message):
        ComplexComponentAblation.model_validate(base, strict=True)


def test_abstained_complex_rejects_each_forbidden_output_family() -> None:
    base = _abstained_complex().model_dump(mode="python")
    cases = (
        (
            {"classification": ComplexTransitionClassification.STABLE},
            "must be not_estimable",
        ),
        ({"coherence": 0.5}, "cannot carry diagnostics"),
        ({"uncertainty": _estimated_uncertainty()}, "uncertainty must be non-estimable"),
        ({"limitations": ()}, "requires reasons only"),
        ({"bootstrap_failed_replicates": 1}, "cannot carry bootstrap failures"),
    )
    for updates, message in cases:
        with pytest.raises(ValidationError, match=message):
            ComplexMemberTransitionConcordance.model_validate(
                {**deepcopy(base), **updates},
                strict=True,
            )


def test_complex_count_and_source_gain_intervals_must_close() -> None:
    base = _estimated_complex().model_dump(mode="python")
    cases = (
        ({"active_member_count": 4}, "counts do not close"),
        (
            {"source_panel_patient_cluster_gain_90_interval": (0.3, 0.1)},
            "gain interval is reversed",
        ),
    )
    for updates, message in cases:
        with pytest.raises(ValidationError, match=message):
            ComplexMemberTransitionConcordance.model_validate(
                {**deepcopy(base), **updates},
                strict=True,
            )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"score": None}, "requires score and interval"),
        ({"score": 0.5}, "interval must contain the score"),
        (
            {"classification": ComplexTransitionClassification.SOURCE_RECURRENCE_ALIGNED},
            "classification must be supported",
        ),
        (
            {"active_member_count": 2, "observed_member_count": 2},
            "does not meet support gates",
        ),
        ({"coefficient_mass_coverage": 0.49}, "does not meet support gates"),
        ({"effective_sample_size": 1.99}, "does not meet support gates"),
        ({"coherence": None}, "requires coherent diagnostics and ablations"),
        ({"least_source_aligned_observed_member": None}, "requires a least-aligned member"),
        ({"limitations": ()}, "limited complex concordance requires a limitation"),
    ],
)
def test_estimated_complex_rejects_incoherent_estimates(updates, message) -> None:
    document = _estimated_complex().model_dump(mode="python")
    document.update(updates)
    with pytest.raises(ValidationError, match=message):
        ComplexMemberTransitionConcordance.model_validate(document, strict=True)


def test_supported_complex_rejects_limitations_and_weak_source_evidence() -> None:
    supported = _estimated_complex(support=AnalysisSupport.SUPPORTED)
    assert supported.support is AnalysisSupport.SUPPORTED
    document = supported.model_dump(mode="python")

    with pytest.raises(ValidationError, match="cannot carry limitations"):
        ComplexMemberTransitionConcordance.model_validate(
            {**deepcopy(document), "limitations": ("unexpected",)},
            strict=True,
        )
    with pytest.raises(ValidationError, match="stable positive held-member evidence"):
        ComplexMemberTransitionConcordance.model_validate(
            {**deepcopy(document), "source_held_member_relative_gain": 0.0},
            strict=True,
        )


def test_transition_panel_requires_source_order_and_unique_reactome_ids() -> None:
    base = _transition().model_dump(mode="python")
    out_of_order = deepcopy(base)
    out_of_order["complexes"][0]["complex_index"] = 1
    with pytest.raises(ValidationError, match="contiguous source-panel order"):
        ComplexTransitionEvidence.model_validate(out_of_order, strict=True)

    duplicate = deepcopy(base)
    second = _abstained_complex(index=1).model_dump(mode="python")
    second["reactome_id"] = duplicate["complexes"][0]["reactome_id"]
    duplicate["complexes"] = (*duplicate["complexes"], second)
    with pytest.raises(ValidationError, match="unique Reactome identifiers"):
        ComplexTransitionEvidence.model_validate(duplicate, strict=True)


def test_result_transition_count_and_adjacency_must_match_time_points() -> None:
    base = _unverified_result().model_dump(mode="python")
    wrong_count = deepcopy(base)
    wrong_count["time_point_ids"] = (*wrong_count["time_point_ids"], "branch.time.2")
    with pytest.raises(ValidationError, match="one transition per adjacent"):
        UnverifiedLongitudinalGbmComplexTransitionResult.model_validate(
            wrong_count,
            strict=True,
        )

    wrong_adjacency = deepcopy(base)
    wrong_adjacency["transitions"][0]["from_time_point_id"] = "branch.time.other"
    with pytest.raises(ValidationError, match="topology does not match"):
        UnverifiedLongitudinalGbmComplexTransitionResult.model_validate(
            wrong_adjacency,
            strict=True,
        )


def test_replay_semantic_summary_must_close_component_checks() -> None:
    with pytest.raises(ValidationError, match="semantic replay flag"):
        ComplexTransitionReplayVerificationResult(
            verified=False,
            request_digest_match=True,
            profile_digest_match=True,
            result_digest_match=True,
            transition_topology_match=True,
            complex_semantic_match=True,
            uncertainty_semantic_match=True,
            ablation_semantic_match=True,
            provenance_match=True,
            document_semantic_match=True,
            semantic_match=False,
            recomputed_request_digest=_DIGEST,
            recomputed_result_digest=_OTHER_DIGEST,
            authoritative_profile_digest=_PROFILE_DIGEST,
            message="inconsistent semantic summary",
        )


def test_profile_panel_order_count_and_digest_are_independently_bound() -> None:
    base = profile_module.algorithm_profile().model_dump(mode="python")

    out_of_order = deepcopy(base)
    out_of_order["complexes"][0]["complex_index"] = 1
    with pytest.raises(ValidationError, match="contiguous source order"):
        LongitudinalGbmComplexTransitionProfile.model_validate(out_of_order, strict=True)

    wrong_count = deepcopy(base)
    wrong_count["counts"]["complex_count"] -= 1
    with pytest.raises(ValidationError, match="complex count does not match"):
        LongitudinalGbmComplexTransitionProfile.model_validate(wrong_count, strict=True)

    wrong_digest = deepcopy(base)
    wrong_digest["profile_digest"] = _DIGEST
    with pytest.raises(ValidationError, match="profile digest mismatch"):
        LongitudinalGbmComplexTransitionProfile.model_validate(wrong_digest, strict=True)


def test_profile_source_decoding_helpers_fail_closed(monkeypatch) -> None:
    with pytest.raises(TypeError, match="is not an object"):
        profile_module._mapping([], "field")
    boolean_value = True
    with pytest.raises(RuntimeError, match="is not numeric"):
        profile_module._number(boolean_value, "field")
    with pytest.raises(RuntimeError, match="is not an integer"):
        profile_module._integer(1.0, "field")

    for raw in (None, [0.1]):
        fitted = SimpleNamespace(
            evaluation={
                "patient_cluster_bootstrap": {"nominal_90_percent_interval": raw},
            },
        )
        monkeypatch.setattr(
            profile_module,
            "complex_transition_fitted_catalog",
            lambda fitted=fitted: fitted,
        )
        with pytest.raises(RuntimeError, match="gain interval must contain two values"):
            profile_module._gain_interval()


def test_profile_rejects_runtime_and_artifact_numpy_version_drift(monkeypatch) -> None:
    monkeypatch.setattr(profile_module.np, "__version__", "0.0.0")
    with pytest.raises(RuntimeError, match=r"requires NumPy 2\.5\.2"):
        profile_module.algorithm_profile()

    monkeypatch.setattr(profile_module.np, "__version__", profile_module.EXPECTED_NUMPY_VERSION)
    monkeypatch.setattr(
        profile_module,
        "complex_transition_fitted_catalog",
        lambda: SimpleNamespace(numpy_version="0.0.0"),
    )
    with pytest.raises(RuntimeError, match="NumPy version is incompatible"):
        profile_module.algorithm_profile()

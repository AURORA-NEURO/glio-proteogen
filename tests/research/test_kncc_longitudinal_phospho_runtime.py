"""Scientific and adversarial tests for the source-locked phosphosite runtime."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from importlib.resources import files as resource_files
from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.research.longitudinal_gbm_phospho import catalog as phospho_catalog
from glio_proteogen.research.longitudinal_gbm_phospho import engine as phospho_engine
from glio_proteogen.research.longitudinal_gbm_phospho.canonical import (
    canonical_request_digest,
)
from glio_proteogen.research.longitudinal_gbm_phospho.catalog import (
    EXPECTED_BOOTSTRAP_DIGEST,
    EXPECTED_CONTENT_DIGEST,
    EXPECTED_CROSSWALK_DIGEST,
    EXPECTED_SOURCE_MANIFEST_DIGEST,
    load_phosphosite_transition_catalog,
)
from glio_proteogen.research.longitudinal_gbm_phospho.contracts import (
    AnalysisSupport,
    LongitudinalGbmPhosphoRequest,
    ModelViewSupport,
    PhosphositeEvidenceState,
    ReplayVerificationRequest,
    TransitionClassification,
    UnverifiedLongitudinalGbmPhosphoResult,
)
from glio_proteogen.research.longitudinal_gbm_phospho.demo import synthetic_demo_request
from glio_proteogen.research.longitudinal_gbm_phospho.errors import (
    PhosphositeIdentityMismatchError,
    UnknownPhosphositeError,
)
from glio_proteogen.research.longitudinal_gbm_phospho.profile import algorithm_profile
from glio_proteogen.research.longitudinal_gbm_phospho.service import (
    analyze_longitudinal_gbm_phospho,
    verify_longitudinal_gbm_phospho_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)


class _MemoryResource:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def joinpath(self, _name: str) -> _MemoryResource:
        return self

    def read_bytes(self) -> bytes:
        return self._payload


class _MemoryFiles:
    def __init__(self, payload: bytes) -> None:
        self._resource = _MemoryResource(payload)

    def __call__(self, _package: str) -> _MemoryResource:
        return self._resource


def test_catalog_fails_closed_and_loads_full_sparse_ensemble() -> None:
    catalog = load_phosphosite_transition_catalog()
    assert catalog.artifact_digest == EXPECTED_CONTENT_DIGEST
    assert catalog.bootstrap_digest == EXPECTED_BOOTSTRAP_DIGEST
    assert catalog.crosswalk_digest == EXPECTED_CROSSWALK_DIGEST
    assert catalog.source_manifest_digest == EXPECTED_SOURCE_MANIFEST_DIGEST
    assert len(catalog.features) == 24_015
    assert len(catalog.selected_features) == catalog.selected_feature_count
    assert len(catalog.bootstrap_projections) == 64
    assert all(
        len(item.feature_indices)
        == len(item.coefficients)
        == len(item.scales)
        == catalog.selected_feature_count
        for item in catalog.bootstrap_projections
    )
    assert sum(abs(item.coefficient) for item in catalog.selected_features) == pytest.approx(1.0)
    suppressed = tuple(item for item in catalog.features if not item.eligible)
    assert suppressed
    assert all(
        item.numerical_release_state == "suppressed_insufficient_support" for item in suppressed
    )
    assert all(
        item.transition_center is None and item.transition_scale is None for item in suppressed
    )
    assert all(
        catalog.features[index].eligible and scale > 0.0
        for projection in catalog.bootstrap_projections
        for index, scale in zip(projection.feature_indices, projection.scales, strict=True)
    )


def test_catalog_rejects_each_runtime_quality_gate_tamper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = (
        resource_files(phospho_catalog.__package__)
        .joinpath(phospho_catalog.ARTIFACT_RESOURCE)
        .read_bytes()
    )
    source_document = cast("dict[str, object]", json.loads(original))
    for gate_name in (
        "selection_stability_passed",
        "bootstrap_full_refit_passed",
        "bootstrap_feature_selection_stability_passed",
        "bootstrap_calibration_passed",
    ):
        document = deepcopy(source_document)
        gates = cast("dict[str, object]", document["runtime_quality_gates"])
        gates[gate_name] = gates[gate_name] is not True
        content = dict(document)
        content.pop("artifact_digest")
        content_digest = phospho_catalog._digest(content)
        document["artifact_digest"] = content_digest
        payload = phospho_catalog._canonical_bytes(document)

        monkeypatch.setattr(phospho_catalog, "files", _MemoryFiles(payload))
        monkeypatch.setattr(phospho_catalog, "EXPECTED_ARTIFACT_BYTES", len(payload))
        monkeypatch.setattr(
            phospho_catalog,
            "EXPECTED_ARTIFACT_SHA256",
            hashlib.sha256(payload).hexdigest(),
        )
        monkeypatch.setattr(phospho_catalog, "EXPECTED_CONTENT_DIGEST", content_digest)
        phospho_catalog.load_phosphosite_transition_catalog.cache_clear()
        with pytest.raises(RuntimeError, match="frozen runtime quality-gate result changed"):
            phospho_catalog.load_phosphosite_transition_catalog()
    phospho_catalog.load_phosphosite_transition_catalog.cache_clear()


def test_profile_binds_exact_assay_source_and_fail_closed_quality_gates() -> None:
    profile = algorithm_profile()
    attestation = profile.required_assay_compatibility
    assert attestation.compatibility_profile_id.startswith("kncc-pdc000515-")
    assert attestation.source_artifact_content_digest == EXPECTED_CONTENT_DIGEST
    assert attestation.value_transformation == "log2_ratio"
    assert attestation.log_base == 2
    assert attestation.composite_site_policy == "indivisible_source_site_group"
    assert profile.claim_ceiling == "raw_phosphosite_transition_concordance_only"
    assert not profile.quality_gates.bootstrap_calibration_passed
    sphinks = profile.sphinks_crosswalk_provenance
    assert "Migliozzi et al." in sphinks.article_attribution
    assert sphinks.article_doi == "10.1038/s43018-022-00510-x"
    assert sphinks.license == "CC-BY-4.0"
    assert sphinks.license_url == "https://creativecommons.org/licenses/by/4.0/"
    assert sphinks.runtime_use == "exact_identity_annotation_only_no_kinase_inference"
    assert "no_shared_reference_covariance" in profile.constants.measurement_covariance_policy


def test_demo_transition_oracle_uncertainty_and_not_fitted_views() -> None:
    result = analyze_longitudinal_gbm_phospho(synthetic_demo_request())
    assert tuple(item.classification for item in result.transitions) == (
        TransitionClassification.SOURCE_RECURRENCE_ALIGNED,
        TransitionClassification.REVERSE_ALIGNED,
        TransitionClassification.STABLE,
    )
    assert all(item.support is AnalysisSupport.LIMITED for item in result.transitions)
    assert result.transitions[0].score == pytest.approx(0.8)
    assert result.transitions[1].score == pytest.approx(-0.65)
    assert result.transitions[2].score == pytest.approx(0.0)
    assert result.transitions[2].censored_feature_count == 2
    assert len(result.transitions[2].censored_bounds) == 2
    assert all(
        item.uncertainty_interaction.decomposition_residual is not None
        and abs(item.uncertainty_interaction.decomposition_residual) <= 2e-8
        for item in result.transitions
    )
    assert tuple(item.support for item in result.model_views) == (
        ModelViewSupport.FITTED,
        ModelViewSupport.NOT_FITTED,
        ModelViewSupport.NOT_FITTED,
    )
    assert result.infers_kinase_activity is False
    assert any("shared-reference" in item for item in result.limitations)
    assert (
        result.provenance.sphinks_crosswalk_provenance
        == algorithm_profile().sphinks_crosswalk_provenance
    )


def test_analysis_and_replay_are_byte_deterministic() -> None:
    request = synthetic_demo_request()
    first = analyze_longitudinal_gbm_phospho(request)
    second = analyze_longitudinal_gbm_phospho(request)
    assert first.model_dump_json() == second.model_dump_json()
    verification = verify_longitudinal_gbm_phospho_replay(
        ReplayVerificationRequest(request=request, result=first)
    )
    assert verification.verified
    assert verification.transition_semantic_match
    assert verification.view_semantic_match


def test_all_four_source_quality_gates_are_fail_closed() -> None:
    catalog = load_phosphosite_transition_catalog()
    all_pass = replace(
        catalog,
        selection_stability_gate_passed=True,
        bootstrap_full_refit_gate_passed=True,
        bootstrap_feature_selection_stability_gate_passed=True,
        bootstrap_calibration_gate_passed=True,
    )
    assert phospho_engine._source_quality_gate(all_pass)
    failed_catalogs = (
        replace(all_pass, selection_stability_gate_passed=False),
        replace(all_pass, bootstrap_full_refit_gate_passed=False),
        replace(all_pass, bootstrap_feature_selection_stability_gate_passed=False),
        replace(all_pass, bootstrap_calibration_gate_passed=False),
    )
    assert all(not phospho_engine._source_quality_gate(item) for item in failed_catalogs)


def test_32_replicates_remain_limited_and_64_are_source_gate_limited() -> None:
    request = synthetic_demo_request()
    short = request.model_copy(update={"bootstrap_replicates": 32})
    short_result = analyze_longitudinal_gbm_phospho(short)
    full_result = analyze_longitudinal_gbm_phospho(request)
    assert all(item.support is AnalysisSupport.LIMITED for item in short_result.transitions)
    assert all(
        any("fewer than 64" in reason for reason in item.abstention_reasons)
        for item in short_result.transitions
    )
    assert all(item.bootstrap_replicates_used == 64 for item in full_result.transitions)


def test_receipt_level_three_component_variance_identity_closes() -> None:
    result = analyze_longitudinal_gbm_phospho(synthetic_demo_request())
    covariances: list[float] = []
    for transition in result.transitions:
        interaction = transition.uncertainty_interaction
        assert transition.measurement_uncertainty.variance is not None
        assert transition.coefficient_uncertainty.variance is not None
        assert interaction.interaction_variance is not None
        assert interaction.interaction_variance_fraction is not None
        assert interaction.variance_contribution is not None
        assert interaction.combined_variance is not None
        assert interaction.decomposed_variance is not None
        assert interaction.decomposition_residual is not None
        decomposed = round(
            transition.measurement_uncertainty.variance
            + transition.coefficient_uncertainty.variance
            + interaction.variance_contribution,
            8,
        )
        assert decomposed == interaction.decomposed_variance
        assert (
            round(decomposed + interaction.decomposition_residual, 8)
            == interaction.combined_variance
        )
        assert transition.measurement_uncertainty.variance_fraction is not None
        assert transition.coefficient_uncertainty.variance_fraction is not None
        assert round(
            transition.measurement_uncertainty.variance_fraction
            + transition.coefficient_uncertainty.variance_fraction
            + interaction.interaction_variance_fraction,
            7,
        ) == pytest.approx(1.0, abs=1e-7)
        covariances.extend(
            (
                interaction.measurement_coefficient_covariance or 0.0,
                interaction.measurement_interaction_covariance or 0.0,
                interaction.coefficient_interaction_covariance or 0.0,
            )
        )
    assert any(value < 0.0 for value in covariances)


def test_pre_cancelled_analysis_stops_at_a_cooperative_checkpoint() -> None:
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        analyze_longitudinal_gbm_phospho(synthetic_demo_request(), cancellation=cancellation)


def test_analysis_checks_cancellation_inside_bootstrap_projection_loop() -> None:
    clock_calls = 0

    def advancing_clock() -> float:
        nonlocal clock_calls
        clock_calls += 1
        return float(clock_calls)

    cancellation = CancellationContext(deadline=3.0, clock=advancing_clock)
    with pytest.raises(InferenceDeadlineExceededError):
        analyze_longitudinal_gbm_phospho(synthetic_demo_request(), cancellation=cancellation)
    assert clock_calls == 3


def test_observation_input_order_is_semantically_invariant() -> None:
    request = synthetic_demo_request()
    reversed_points = tuple(
        point.model_copy(update={"observations": tuple(reversed(point.observations))})
        for point in request.time_points
    )
    reordered = request.model_copy(update={"time_points": reversed_points})
    assert canonical_request_digest(reordered) == request.request_digest
    assert (
        analyze_longitudinal_gbm_phospho(reordered).result_digest
        == analyze_longitudinal_gbm_phospho(request).result_digest
    )


def test_main_projection_matches_independent_frozen_sparse_calculation() -> None:
    request = synthetic_demo_request()
    catalog = load_phosphosite_transition_catalog()
    left = {item.phosphosite_id: item for item in request.time_points[0].observations}
    right = {item.phosphosite_id: item for item in request.time_points[1].observations}
    numerator = 0.0
    denominator = 0.0
    for feature in catalog.selected_features:
        assert feature.transition_scale is not None
        left_value = left[feature.phosphosite_id].log_abundance_ratio
        right_value = right[feature.phosphosite_id].log_abundance_ratio
        assert left_value is not None and right_value is not None
        numerator += feature.coefficient * (right_value - left_value) / feature.transition_scale
        denominator += abs(feature.coefficient)
    expected = round(numerator / denominator, 8)
    observed = analyze_longitudinal_gbm_phospho(request).transitions[0]
    assert observed.score == expected


def test_one_sided_censoring_preserves_coefficient_aware_bounds() -> None:
    request = synthetic_demo_request()
    catalog = load_phosphosite_transition_catalog()
    positive = next(item for item in catalog.selected_features if item.coefficient > 0.0)
    censored_ids = {positive.phosphosite_id}
    first = request.time_points[0]
    observations = tuple(
        item.model_copy(update={"state": PhosphositeEvidenceState.LEFT_CENSORED})
        if item.phosphosite_id in censored_ids
        else item
        for item in first.observations
    )
    changed = request.model_copy(
        update={
            "time_points": (
                first.model_copy(update={"observations": observations}),
                *request.time_points[1:],
            )
        }
    )
    transition = analyze_longitudinal_gbm_phospho(changed).transitions[0]
    by_site = {item.phosphosite_id: item for item in transition.censored_bounds}
    assert by_site[positive.phosphosite_id].value_semantics == "lower_bound"
    assert transition.exact_feature_count == catalog.selected_feature_count - 1
    flipped_semantics, weighted = phospho_engine._coefficient_weighted_bound(
        "lower_bound", 1.25, -0.4
    )
    assert flipped_semantics == "upper_bound"
    assert weighted == pytest.approx(-0.5)


def test_contract_rejects_duplicate_sites_offsets_and_reference_drift() -> None:
    payload = synthetic_demo_request().model_dump(mode="json")
    payload["time_points"][0]["observations"][1]["phosphosite_id"] = payload["time_points"][0][
        "observations"
    ][0]["phosphosite_id"]
    with pytest.raises(ValidationError):
        LongitudinalGbmPhosphoRequest.model_validate_json(json.dumps(payload))

    payload = synthetic_demo_request().model_dump(mode="json")
    payload["time_points"][1]["time_offset_days"] = payload["time_points"][0]["time_offset_days"]
    with pytest.raises(ValidationError):
        LongitudinalGbmPhosphoRequest.model_validate_json(json.dumps(payload))

    payload = synthetic_demo_request().model_dump(mode="json")
    payload["time_points"][1]["normalization_reference_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValidationError):
        LongitudinalGbmPhosphoRequest.model_validate_json(json.dumps(payload))


def test_missing_and_unsupported_are_not_negative_observations() -> None:
    request = synthetic_demo_request()
    selected_ids = {
        item.phosphosite_id for item in load_phosphosite_transition_catalog().selected_features
    }
    keep_count = max(1, len(selected_ids) // 4)
    kept = set(sorted(selected_ids)[:keep_count])
    changed_points = []
    for point_index, point in enumerate(request.time_points):
        observations = list(point.observations)
        for index, observation in enumerate(observations):
            if observation.phosphosite_id not in selected_ids - kept:
                continue
            state = (
                PhosphositeEvidenceState.MISSING
                if (index + point_index) % 2 == 0
                else PhosphositeEvidenceState.UNSUPPORTED
            )
            observations[index] = observations[index].model_copy(
                update={
                    "state": state,
                    "log_abundance_ratio": None,
                    "standard_error": None,
                    "quality_weight": 0.0,
                }
            )
        changed_points.append(point.model_copy(update={"observations": tuple(observations)}))
    changed = request.model_copy(update={"time_points": tuple(changed_points)})
    result = analyze_longitudinal_gbm_phospho(changed)
    assert all(item.support is AnalysisSupport.ABSTAINED for item in result.transitions)
    assert all(item.score is None for item in result.transitions)


def test_unknown_site_and_wrong_gene_fail_closed() -> None:
    request = synthetic_demo_request()
    point = request.time_points[0]
    observation = point.observations[0]
    unknown = observation.model_copy(update={"phosphosite_id": "ENSP99999999999.1:s1"})
    unknown_request = request.model_copy(
        update={
            "time_points": (
                point.model_copy(update={"observations": (unknown, *point.observations[1:])}),
                *request.time_points[1:],
            )
        }
    )
    with pytest.raises(UnknownPhosphositeError):
        analyze_longitudinal_gbm_phospho(unknown_request)

    wrong_gene = observation.model_copy(update={"gene_symbol": "TP53"})
    mismatch_request = request.model_copy(
        update={
            "time_points": (
                point.model_copy(update={"observations": (wrong_gene, *point.observations[1:])}),
                *request.time_points[1:],
            )
        }
    )
    with pytest.raises(PhosphositeIdentityMismatchError):
        analyze_longitudinal_gbm_phospho(mismatch_request)


def test_assay_attestation_has_no_defaults_and_rejects_drift() -> None:
    payload = synthetic_demo_request().model_dump(mode="json")
    del payload["assay_compatibility"]["quantification"]
    with pytest.raises(ValidationError):
        LongitudinalGbmPhosphoRequest.model_validate_json(json.dumps(payload))
    payload = synthetic_demo_request().model_dump(mode="json")
    payload["assay_compatibility"]["log_base"] = 10
    with pytest.raises(ValidationError):
        LongitudinalGbmPhosphoRequest.model_validate_json(json.dumps(payload))


def test_forged_receipt_is_recomputed_and_rejected() -> None:
    request = synthetic_demo_request()
    result = analyze_longitudinal_gbm_phospho(request)
    payload = deepcopy(result.model_dump(mode="json"))
    payload["result_digest"] = "sha256:" + "0" * 64
    unverified = UnverifiedLongitudinalGbmPhosphoResult.model_validate_json(json.dumps(payload))
    verification = verify_longitudinal_gbm_phospho_replay(
        ReplayVerificationRequest(request=request, result=unverified)
    )
    assert not verification.verified
    assert not verification.result_digest_match


def test_driver_ablations_and_exact_sphinks_annotations_are_bounded() -> None:
    transition = analyze_longitudinal_gbm_phospho(synthetic_demo_request()).transitions[0]
    assert 1 <= len(transition.top_drivers) <= 10
    assert len(transition.top_driver_ablations) == len(transition.top_drivers)
    assert {item.component for item in transition.feature_family_ablations} == {
        "composite_site_groups",
        "exact_sphinks_crosswalk_sites",
    }
    assert all(item.value_semantics == "exact_delta" for item in transition.top_drivers)
    catalog = load_phosphosite_transition_catalog()
    assert any(item.sphinks_source_site_label is not None for item in catalog.selected_features)
    for driver in transition.top_drivers:
        feature = catalog.feature_by_id[driver.phosphosite_id]
        assert driver.sphinks_source_site_label == feature.sphinks_source_site_label
        assert driver.sphinks_signature_kinases == feature.sphinks_signature_kinases

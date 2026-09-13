from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from importlib.resources import files as resource_files

import pytest
from pydantic import ValidationError

from glio_proteogen.research.longitudinal_gbm_kinase_transition import catalog as catalog_module
from glio_proteogen.research.longitudinal_gbm_kinase_transition import engine
from glio_proteogen.research.longitudinal_gbm_kinase_transition.canonical import (
    canonical_request_digest,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.catalog import (
    EXPECTED_ARTIFACT_BYTES,
    EXPECTED_ARTIFACT_SHA256,
    EXPECTED_BOOTSTRAP_DIGEST,
    EXPECTED_CONTENT_DIGEST,
    EXPECTED_FITTER_SOURCE_SHA256,
    load_kinase_transition_catalog,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.contracts import (
    AnalysisSupport,
    BootstrapState,
    KinaseSelectionState,
    LongitudinalGbmKinaseTransitionRequest,
    ReplayVerificationRequest,
    TransitionClassification,
    UnverifiedLongitudinalGbmKinaseTransitionResult,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.demo import (
    DEMO_SEMANTIC_ORACLE_DIGEST,
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.errors import (
    PhosphositeIdentityMismatchError,
    SourceProfileIntegrityError,
    UnknownPhosphositeError,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.profile import (
    algorithm_profile,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.service import (
    analyze_longitudinal_gbm_kinase_transition,
    verify_longitudinal_gbm_kinase_transition_replay,
)
from glio_proteogen.research.longitudinal_gbm_phospho.contracts import (
    PhosphositeEvidenceState,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)


def test_catalog_locks_source_counts_bh_and_bootstrap_ensemble() -> None:
    catalog = load_kinase_transition_catalog()
    assert catalog.artifact_sha256 == f"sha256:{EXPECTED_ARTIFACT_SHA256}"
    assert catalog.artifact_digest == EXPECTED_CONTENT_DIGEST
    assert catalog.bootstrap_digest == EXPECTED_BOOTSTRAP_DIGEST
    assert len(catalog.families) == 2_457
    assert len(catalog.hypotheses) == 24
    assert len(catalog.selected_kinases) == 12
    assert len(catalog.bootstrap_projections) == 64
    assert catalog.counts["strict_patient_pairs"] == 88
    assert catalog.counts["exact_crosswalk_pdc_rows"] == 8_779
    assert catalog.counts["unique_crosswalk_families"] == 8_533
    assert catalog.counts["duplicate_family_extra_pdc_rows"] == 246
    assert catalog.counts["signature_pdc_rows"] == 608
    assert catalog.counts["unique_signature_families"] == 572
    selected = {item.kinase for item in catalog.hypotheses if item.selected}
    assert selected == {item.kinase for item in catalog.selected_kinases}
    assert all(item.q_value <= 0.10 for item in catalog.hypotheses if item.selected)
    assert all(item.q_value > 0.10 for item in catalog.hypotheses if not item.selected)


def test_artifact_is_compact_canonical_and_contains_no_patient_pseudonym() -> None:
    resource = resource_files(
        "glio_proteogen.research.longitudinal_gbm_kinase_transition"
    ).joinpath("data/kncc_sphinks_signature_transition.v1.json")
    payload = resource.read_bytes()
    assert len(payload) == EXPECTED_ARTIFACT_BYTES
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_ARTIFACT_SHA256
    assert b"KNCC_GBM" not in payload.upper()
    document = json.loads(payload)
    assert document["privacy"] == {
        "aggregate_and_release_eligible_parameters_only": True,
        "patient_derived_digests_emitted": False,
        "patient_identifiers_emitted": False,
        "patient_level_matrices_emitted": False,
    }
    assert len(payload) < 2 * 1_024 * 1_024


def test_profile_is_exactly_source_bound_and_fail_closed() -> None:
    profile = algorithm_profile()
    assert profile.counts.fixed_master_kinase_hypotheses == 24
    assert profile.digests.fitter_source_sha256 == EXPECTED_FITTER_SOURCE_SHA256
    assert profile.counts.full_fit_selected_kinases == 12
    assert profile.counts.core_stable_selected_kinases == 11
    assert profile.quality_gates.same_assay_independent_evidence_gate_passed is False
    assert profile.quality_gates.patient_bootstrap_full_refit_convergence_gate_passed
    assert profile.quality_gates.patient_bootstrap_full_set_stability_gate_passed is False
    assert profile.quality_gates.patient_bootstrap_interval_calibration_gate_passed is False
    assert profile.demo_semantic_oracle_digest == DEMO_SEMANTIC_ORACLE_DIGEST
    assert profile.claim_ceiling == "SPHINKS_signature_transition_concordance_only"
    assert "Migliozzi" in profile.source_provenance.sphinks_article_attribution
    assert "10.1038/s43018-022-00510-x" in profile.source_provenance.sphinks_article_attribution


def test_demo_has_expected_limited_transition_semantics_and_chek2() -> None:
    result = analyze_longitudinal_gbm_kinase_transition(synthetic_demo_request())
    assert [item.classification for item in result.transitions] == [
        TransitionClassification.SOURCE_RECURRENCE_ALIGNED,
        TransitionClassification.REVERSE_ALIGNED,
        TransitionClassification.SOURCE_RECURRENCE_ALIGNED,
    ]
    assert all(item.support is AnalysisSupport.LIMITED for item in result.transitions)
    assert all(item.uncertainty.bootstrap_replicates_used == 64 for item in result.transitions)
    first = result.transitions[0]
    assert len(first.kinase_signatures) == 24
    assert first.selected_kinase_count == 12
    assert first.estimable_kinase_count == 12
    selected = [
        item
        for item in first.kinase_signatures
        if item.selection_state is not KinaseSelectionState.NOT_SELECTED
    ]
    assert len(selected) == 12
    chek2 = next(item for item in selected if item.kinase == "CHEK2")
    assert chek2.selection_state is KinaseSelectionState.SELECTED_UNSTABLE
    assert chek2.support is AnalysisSupport.LIMITED
    assert chek2.bootstrap_selection_frequency == 0.546875
    assert any("0.80" in reason for reason in chek2.reasons)
    assert all(
        item.support is AnalysisSupport.ABSTAINED
        for item in first.kinase_signatures
        if item.selection_state is KinaseSelectionState.NOT_SELECTED
    )


def test_result_claim_ceiling_and_provenance_are_explicit() -> None:
    result = analyze_longitudinal_gbm_kinase_transition(synthetic_demo_request())
    assert result.infers_kinase_activity is False
    assert result.infers_biochemical_activity is False
    assert result.makes_causal_claim is False
    assert result.independent_evidence is False
    assert any("not independent evidence" in item for item in result.limitations)
    assert any("shared-reference" in item for item in result.limitations)
    assert any("Composite" in item for item in result.limitations)
    assert result.provenance.source_provenance == algorithm_profile().source_provenance


def test_analysis_and_replay_are_byte_deterministic() -> None:
    request = synthetic_demo_request()
    first = analyze_longitudinal_gbm_kinase_transition(request)
    second = analyze_longitudinal_gbm_kinase_transition(request)
    assert first.model_dump_json() == second.model_dump_json()
    replay = verify_longitudinal_gbm_kinase_transition_replay(
        ReplayVerificationRequest(request=request, result=first)
    )
    assert replay.verified
    assert replay.transition_semantic_match
    assert replay.semantic_match


def test_forged_result_never_verifies() -> None:
    request = synthetic_demo_request()
    result = analyze_longitudinal_gbm_kinase_transition(request)
    document = result.model_dump(mode="json")
    document["result_digest"] = "sha256:" + "0" * 64
    forged = UnverifiedLongitudinalGbmKinaseTransitionResult.model_validate_json(
        json.dumps(document)
    )
    replay = verify_longitudinal_gbm_kinase_transition_replay(
        ReplayVerificationRequest(request=request, result=forged)
    )
    assert not replay.verified
    assert not replay.result_digest_match


def test_observation_input_order_is_semantically_invariant() -> None:
    request = synthetic_demo_request()
    reversed_points = tuple(
        point.model_copy(update={"observations": tuple(reversed(point.observations))})
        for point in request.time_points
    )
    reordered = request.model_copy(update={"time_points": reversed_points})
    assert canonical_request_digest(reordered) == request.request_digest
    assert (
        analyze_longitudinal_gbm_kinase_transition(reordered).result_digest
        == analyze_longitudinal_gbm_kinase_transition(request).result_digest
    )


def test_32_and_64_patient_bootstraps_remain_limited() -> None:
    request = synthetic_demo_request()
    short = request.model_copy(update={"bootstrap_replicates": 32})
    short_result = analyze_longitudinal_gbm_kinase_transition(short)
    full_result = analyze_longitudinal_gbm_kinase_transition(request)
    assert all(item.support is AnalysisSupport.LIMITED for item in short_result.transitions)
    assert all(
        item.uncertainty.bootstrap_replicates_used == 32 for item in short_result.transitions
    )
    assert all(item.uncertainty.bootstrap_replicates_used == 64 for item in full_result.transitions)


def test_missing_and_unsupported_evidence_cannot_become_negative() -> None:
    request = synthetic_demo_request()
    points = []
    for point in request.time_points:
        observations = tuple(
            item.model_copy(
                update={
                    "state": PhosphositeEvidenceState.MISSING,
                    "log_abundance_ratio": None,
                    "standard_error": None,
                    "quality_weight": 0.0,
                }
            )
            for item in point.observations
        )
        points.append(point.model_copy(update={"observations": observations}))
    missing_request = request.model_copy(update={"time_points": tuple(points)})
    result = analyze_longitudinal_gbm_kinase_transition(missing_request)
    assert all(item.support is AnalysisSupport.ABSTAINED for item in result.transitions)
    assert all(item.score is None for item in result.transitions)
    assert all(
        item.classification is TransitionClassification.NOT_ESTIMABLE for item in result.transitions
    )


def test_sparse_overlap_abstains_instead_of_extrapolating() -> None:
    request = synthetic_demo_request()
    points = tuple(
        point.model_copy(update={"observations": point.observations[:2]})
        for point in request.time_points
    )
    sparse = request.model_copy(update={"time_points": points})
    result = analyze_longitudinal_gbm_kinase_transition(sparse)
    assert all(item.support is AnalysisSupport.ABSTAINED for item in result.transitions)
    assert all(
        item.uncertainty.state is BootstrapState.NOT_ESTIMABLE for item in result.transitions
    )
    selected = {
        item.kinase: item.selection_state
        for item in result.transitions[0].kinase_signatures
        if item.selection_state is not KinaseSelectionState.NOT_SELECTED
    }
    assert len(selected) == 12
    assert selected["CHEK2"] is KinaseSelectionState.SELECTED_UNSTABLE


def test_interval_abstention_preserves_frozen_source_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = load_kinase_transition_catalog()
    without_bootstraps = replace(catalog, bootstrap_projections=())
    monkeypatch.setattr(
        engine,
        "load_kinase_transition_catalog",
        lambda: without_bootstraps,
    )

    result = analyze_longitudinal_gbm_kinase_transition(synthetic_demo_request())
    first = result.transitions[0]
    assert first.support is AnalysisSupport.ABSTAINED
    assert first.uncertainty.state is BootstrapState.NOT_ESTIMABLE
    selected = {
        item.kinase: item.selection_state
        for item in first.kinase_signatures
        if item.selection_state is not KinaseSelectionState.NOT_SELECTED
    }
    assert len(selected) == 12
    assert selected["CHEK2"] is KinaseSelectionState.SELECTED_UNSTABLE
    assert selected["GSK3B"] is KinaseSelectionState.SELECTED_CORE


def test_unknown_site_and_gene_identity_drift_fail_closed() -> None:
    request = synthetic_demo_request()
    point = request.time_points[0]
    unknown = point.observations[0].model_copy(update={"phosphosite_id": "ENSP999999999.1:s1"})
    unknown_request = request.model_copy(
        update={
            "time_points": (
                point.model_copy(update={"observations": (unknown, *point.observations[1:])}),
                *request.time_points[1:],
            )
        }
    )
    with pytest.raises(UnknownPhosphositeError, match="unknown exact"):
        analyze_longitudinal_gbm_kinase_transition(unknown_request)
    mismatch = point.observations[0].model_copy(update={"gene_symbol": "TP53"})
    mismatch_request = request.model_copy(
        update={
            "time_points": (
                point.model_copy(update={"observations": (mismatch, *point.observations[1:])}),
                *request.time_points[1:],
            )
        }
    )
    with pytest.raises(PhosphositeIdentityMismatchError, match="HGNC"):
        analyze_longitudinal_gbm_kinase_transition(mismatch_request)


def test_request_contract_rejects_duplicate_ids_offsets_and_assay_drift() -> None:
    request = synthetic_demo_request()
    document = request.model_dump(mode="python")
    document["time_points"][1]["time_point_id"] = document["time_points"][0]["time_point_id"]
    with pytest.raises(ValidationError, match="time-point identifiers"):
        LongitudinalGbmKinaseTransitionRequest.model_validate(document)
    document = request.model_dump(mode="python")
    document["time_points"][1]["time_offset_days"] = 0.0
    with pytest.raises(ValidationError, match="strictly increasing"):
        LongitudinalGbmKinaseTransitionRequest.model_validate(document)
    document = request.model_dump(mode="python")
    document["assay_compatibility"]["log_base"] = 10
    with pytest.raises(ValidationError):
        LongitudinalGbmKinaseTransitionRequest.model_validate(document)


def test_pre_cancelled_and_inner_projection_cancellation_are_cooperative() -> None:
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        analyze_longitudinal_gbm_kinase_transition(
            synthetic_demo_request(), cancellation=cancellation
        )

    ticks = iter([0.0, 0.0, 0.0, 0.0, 4.0])

    def advancing_clock() -> float:
        return next(ticks, 4.0)

    deadline = CancellationContext(deadline=3.0, clock=advancing_clock)
    with pytest.raises(InferenceDeadlineExceededError):
        analyze_longitudinal_gbm_kinase_transition(synthetic_demo_request(), cancellation=deadline)


def test_ablation_family_is_fixed_and_all_outputs_are_non_supported() -> None:
    result = analyze_longitudinal_gbm_kinase_transition(synthetic_demo_request())
    for transition in result.transitions:
        assert [item.ablation for item in transition.ablations] == [
            "equal_kinase_instead_of_equal_subtype",
            "omit_composite_source_groups",
            "omit_inverse_multiplicity_correction",
        ]
        assert all(item.support is not None for item in transition.ablations)
        assert transition.support is not AnalysisSupport.ABSTAINED


def test_catalog_byte_tampering_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = load_kinase_transition_catalog()
    assert catalog.bootstrap_digest == EXPECTED_BOOTSTRAP_DIGEST
    resource = resource_files(catalog_module.__package__).joinpath(catalog_module.ARTIFACT_RESOURCE)
    payload = bytearray(resource.read_bytes())
    payload[len(payload) // 2] ^= 1

    class _TamperedResource:
        def joinpath(self, _name: str) -> _TamperedResource:
            return self

        def read_bytes(self) -> bytes:
            return bytes(payload)

    catalog_module.load_kinase_transition_catalog.cache_clear()
    monkeypatch.setattr(catalog_module, "files", lambda _package: _TamperedResource())
    with pytest.raises(SourceProfileIntegrityError, match="byte digest"):
        catalog_module.load_kinase_transition_catalog()
    catalog_module.load_kinase_transition_catalog.cache_clear()

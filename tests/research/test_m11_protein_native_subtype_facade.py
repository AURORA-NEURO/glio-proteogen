"""Unit contract tests for the additive M11 protein-axis evidence facade."""

from __future__ import annotations

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbm_proteomic_axes import (
    GbmReplayVerificationRequest,
    analyze_gbm_proteomic_axes,
    synthetic_demo_request,
    verify_gbm_proteomic_axes_replay,
)
from glio_proteogen.research.m11_protein_native_subtype_facade import (
    M11ResponsibilityDisposition,
    analyze_m11_protein_axis_evidence,
    m11_facade_demo,
    m11_facade_profile,
    verify_m11_protein_axis_replay,
)


def test_profile_binds_exact_delegation_and_conservative_m11_ceiling() -> None:
    profile = m11_facade_profile()
    dumped = profile.model_dump(mode="json")
    digest_payload = {key: value for key, value in dumped.items() if key != "facade_profile_digest"}

    assert profile.delegated_profile.profile_id == "gbm-proteomic-axes/1.0.0"
    assert profile.delegated_profile_digest == profile.delegated_profile.profile_digest
    assert profile.facade_profile_digest == sha256_digest(digest_payload)
    assert profile.delegation.exact_request_passthrough is True
    assert profile.delegation.exact_result_passthrough is True
    assert profile.delegation.exact_replay_passthrough is True
    assert profile.delegation.published_model_license == "MIT"
    assert profile.claim_ceiling.supplies_published_protein_axis_evidence is True
    assert profile.claim_ceiling.can_replace_synthetic_or_caller_declared_axis_scores is True
    assert profile.claim_ceiling.emits_posterior_subtype_classifier is False
    assert profile.claim_ceiling.infers_longitudinal_evolution is False
    assert profile.claim_ceiling.emits_clinical_class is False
    assert profile.claim_ceiling.governed_m11_replacement is False

    boundaries = {item.module_id: item for item in profile.responsibility_boundaries}
    assert set(boundaries) == {f"GLIO-PROTEOGEN-M11-{index:02d}" for index in range(1, 9)}
    assert all(item.module_responsibility_superseded is False for item in boundaries.values())
    assert (
        boundaries["GLIO-PROTEOGEN-M11-02"].disposition
        is M11ResponsibilityDisposition.AXIS_EVIDENCE_SUBSTITUTION_ONLY
    )
    assert (
        boundaries["GLIO-PROTEOGEN-M11-05"].disposition is M11ResponsibilityDisposition.OUT_OF_SCOPE
    )
    assert (
        boundaries["GLIO-PROTEOGEN-M11-06"].disposition is M11ResponsibilityDisposition.OUT_OF_SCOPE
    )


def test_demo_analysis_and_replay_are_exact_delegations() -> None:
    assert m11_facade_demo() is synthetic_demo_request()
    request = m11_facade_demo().model_copy(update={"bootstrap_replicates": 0})

    direct_result = analyze_gbm_proteomic_axes(request)
    facade_result = analyze_m11_protein_axis_evidence(request)

    assert facade_result == direct_result
    assert facade_result.request_digest == request.request_digest
    assert facade_result.profile_digest == m11_facade_profile().delegated_profile_digest
    assert facade_result.result_digest == direct_result.result_digest

    envelope = GbmReplayVerificationRequest(request=request, result=facade_result)
    direct_replay = verify_gbm_proteomic_axes_replay(envelope)
    facade_replay = verify_m11_protein_axis_replay(envelope)

    assert facade_replay == direct_replay
    assert facade_replay.verified is True
    assert facade_replay.recomputed_request_digest == request.request_digest
    assert facade_replay.recomputed_result_digest == facade_result.result_digest

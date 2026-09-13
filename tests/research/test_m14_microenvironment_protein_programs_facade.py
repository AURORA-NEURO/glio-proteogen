"""Unit contract tests for the additive M14 protein-program facade."""

from __future__ import annotations

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.m14_microenvironment_protein_programs_facade import (
    M14ResponsibilityDisposition,
    analyze_m14_microenvironment_program_evidence,
    m14_facade_demo,
    m14_facade_profile,
    verify_m14_microenvironment_program_replay,
)
from glio_proteogen.research.neftel_protein_programs import (
    ReplayVerificationRequest,
    analyze_neftel_protein_programs,
    synthetic_demo_request,
    verify_neftel_protein_program_replay,
)


def test_profile_binds_exact_delegation_and_conservative_m14_ceiling() -> None:
    profile = m14_facade_profile()
    dumped = profile.model_dump(mode="json")
    digest_payload = {key: value for key, value in dumped.items() if key != "facade_profile_digest"}

    assert profile.delegated_profile.profile_id == "neftel-bulk-protein-programs/1.0.0"
    assert profile.delegated_profile_digest == profile.delegated_profile.profile_digest
    assert profile.facade_profile_digest == sha256_digest(digest_payload)
    assert profile.output_semantics == "bulk_protein_program_evidence"
    assert profile.delegation.exact_request_passthrough is True
    assert profile.delegation.exact_result_passthrough is True
    assert profile.delegation.exact_replay_passthrough is True
    assert profile.claim_ceiling.supplies_bulk_protein_program_concordance is True
    assert profile.claim_ceiling.can_replace_synthetic_or_caller_declared_program_scores is True
    assert profile.claim_ceiling.emits_cell_fractions is False
    assert profile.claim_ceiling.performs_deconvolution is False
    assert profile.claim_ceiling.estimates_cell_abundance is False
    assert profile.claim_ceiling.emits_spatial_localization is False
    assert profile.claim_ceiling.infers_immune_composition is False
    assert profile.claim_ceiling.emits_clinical_class is False
    assert profile.claim_ceiling.recommends_treatment is False
    assert profile.claim_ceiling.governed_m14_replacement is False

    boundaries = {item.module_id: item for item in profile.responsibility_boundaries}
    assert set(boundaries) == {f"GLIO-PROTEOGEN-M14-{index:02d}" for index in range(1, 9)}
    assert all(item.module_responsibility_superseded is False for item in boundaries.values())
    assert (
        boundaries["GLIO-PROTEOGEN-M14-02"].disposition
        is M14ResponsibilityDisposition.PROGRAM_EVIDENCE_SUBSTITUTION_ONLY
    )
    assert (
        boundaries["GLIO-PROTEOGEN-M14-05"].disposition is M14ResponsibilityDisposition.OUT_OF_SCOPE
    )
    assert (
        boundaries["GLIO-PROTEOGEN-M14-06"].disposition is M14ResponsibilityDisposition.OUT_OF_SCOPE
    )


def test_demo_analysis_and_replay_are_exact_delegations() -> None:
    assert m14_facade_demo() is synthetic_demo_request()
    request = m14_facade_demo()

    direct_result = analyze_neftel_protein_programs(request)
    facade_result = analyze_m14_microenvironment_program_evidence(request)

    assert facade_result == direct_result
    assert facade_result.request_digest == request.request_digest
    assert facade_result.profile_digest == m14_facade_profile().delegated_profile_digest
    assert facade_result.result_digest == direct_result.result_digest
    assert facade_result.output_semantics == "bulk_protein_program_evidence"

    envelope = ReplayVerificationRequest(request=request, result=facade_result)
    direct_replay = verify_neftel_protein_program_replay(envelope)
    facade_replay = verify_m14_microenvironment_program_replay(envelope)

    assert facade_replay == direct_replay
    assert facade_replay.verified is True
    assert facade_replay.recomputed_request_digest == request.request_digest
    assert facade_replay.recomputed_result_digest == facade_result.result_digest

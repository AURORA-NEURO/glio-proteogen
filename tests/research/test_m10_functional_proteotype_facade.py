"""Unit contract tests for the additive M10 functional-proteotype facade."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbm_functional_proteotype import (
    ReplayVerificationRequest,
    analyze_functional_proteotype,
    synthetic_demo_request,
    verify_functional_proteotype_replay,
)
from glio_proteogen.research.m10_functional_proteotype_facade import (
    M10ResponsibilityDisposition,
    analyze_m10_functional_proteotype_evidence,
    m10_facade_demo,
    m10_facade_profile,
    verify_m10_functional_proteotype_replay,
)


def test_profile_binds_exact_delegation_and_conservative_m10_ceiling() -> None:
    profile = m10_facade_profile()
    dumped = profile.model_dump(mode="json")
    digest_payload = {key: value for key, value in dumped.items() if key != "facade_profile_digest"}

    assert profile.delegated_profile.profile_id == "migliozzi-gbm-functional-proteotype/1.0.0"
    assert profile.delegated_profile_digest == profile.delegated_profile.profile_digest
    assert profile.facade_profile_digest == sha256_digest(digest_payload)
    assert profile.output_semantics == "bulk_gbm_functional_proteotype_evidence"
    assert profile.delegation.engine_profile_id == "migliozzi-gbm-functional-proteotype/1.0.0"
    assert profile.delegation.request_contract == "FunctionalProteotypeRequest"
    assert profile.delegation.result_contract == "FunctionalProteotypeResult"
    assert profile.delegation.replay_request_contract == "ReplayVerificationRequest"
    assert profile.delegation.replay_result_contract == "ReplayVerificationResult"
    assert profile.delegation.exact_request_passthrough is True
    assert profile.delegation.exact_result_passthrough is True
    assert profile.delegation.exact_replay_passthrough is True
    assert profile.delegation.source_evidence_license == "CC-BY-4.0"
    assert profile.claim_ceiling.supplies_source_locked_four_axis_protein_concordance is True
    assert (
        profile.claim_ceiling.can_replace_synthetic_or_caller_declared_m10_03_m10_07_numerical_stand_ins
        is True
    )
    assert profile.claim_ceiling.emits_sample_pathway_activation is False
    assert profile.claim_ceiling.emits_posterior_subtype is False
    assert profile.claim_ceiling.infers_mechanism is False
    assert profile.claim_ceiling.infers_causal_perturbation is False
    assert profile.claim_ceiling.emits_prognosis is False
    assert profile.claim_ceiling.recommends_treatment is False
    assert profile.claim_ceiling.governed_m10_replacement is False

    boundaries = {item.module_id: item for item in profile.responsibility_boundaries}
    assert set(boundaries) == {f"GLIO-PROTEOGEN-M10-{index:02d}" for index in range(1, 9)}
    assert all(item.module_responsibility_superseded is False for item in boundaries.values())
    for module_id in ("GLIO-PROTEOGEN-M10-03", "GLIO-PROTEOGEN-M10-07"):
        assert (
            boundaries[module_id].disposition
            is M10ResponsibilityDisposition.RESEARCH_NUMERICAL_STAND_IN_SUBSTITUTION_ONLY
        )
    for boundary in (
        boundaries["GLIO-PROTEOGEN-M10-01"],
        boundaries["GLIO-PROTEOGEN-M10-02"],
        boundaries["GLIO-PROTEOGEN-M10-04"],
        boundaries["GLIO-PROTEOGEN-M10-05"],
        boundaries["GLIO-PROTEOGEN-M10-06"],
        boundaries["GLIO-PROTEOGEN-M10-08"],
    ):
        assert boundary.disposition is M10ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("boundary_order", "complete and ordered"),
        ("delegated_digest", "does not match the Migliozzi profile"),
        ("facade_digest", "does not match canonical profile content"),
    ],
)
def test_profile_rejects_forged_content_binding(mutation: str, message: str) -> None:
    profile_type = type(m10_facade_profile())
    payload = m10_facade_profile().model_dump(mode="python")
    if mutation == "boundary_order":
        boundaries = payload["responsibility_boundaries"]
        payload["responsibility_boundaries"] = (
            boundaries[1],
            boundaries[0],
            *boundaries[2:],
        )
    elif mutation == "delegated_digest":
        payload["delegated_profile_digest"] = "sha256:" + ("0" * 64)
    else:
        payload["facade_profile_digest"] = "sha256:" + ("0" * 64)

    with pytest.raises(ValidationError, match=message):
        profile_type.model_validate(payload)


def test_demo_analysis_and_replay_are_exact_delegations() -> None:
    assert m10_facade_demo() is synthetic_demo_request()
    request = m10_facade_demo().model_copy(
        update={"bootstrap_replicates": 16, "permutation_replicates": 64}
    )

    direct_result = analyze_functional_proteotype(request)
    facade_result = analyze_m10_functional_proteotype_evidence(request)

    assert facade_result == direct_result
    assert facade_result.request_digest == request.request_digest
    assert facade_result.profile_digest == m10_facade_profile().delegated_profile_digest
    assert facade_result.result_digest == direct_result.result_digest
    assert facade_result.output_semantics == "bulk_gbm_functional_proteotype_evidence"

    envelope = ReplayVerificationRequest(request=request, result=facade_result)
    direct_replay = verify_functional_proteotype_replay(envelope)
    facade_replay = verify_m10_functional_proteotype_replay(envelope)

    assert facade_replay == direct_replay
    assert facade_replay.verified is True
    assert facade_replay.recomputed_request_digest == request.request_digest
    assert facade_replay.recomputed_result_digest == facade_result.result_digest

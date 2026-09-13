"""Contract tests for the additive M15 longitudinal-evidence facade."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.longitudinal_gbm import ReplayVerificationRequest
from glio_proteogen.research.longitudinal_gbm.m15_facade import (
    M15LongitudinalRecurrenceFacadeProfile,
    M15ResponsibilityDisposition,
    analyze_m15_longitudinal_recurrence_evidence,
    m15_facade_demo,
    m15_facade_profile,
    verify_m15_longitudinal_recurrence_replay,
)
from glio_proteogen.research.longitudinal_gbm.service import (
    analyze_longitudinal_gbm,
    verify_longitudinal_gbm_replay,
)


def test_profile_binds_exact_engine_and_conservative_m15_ceiling() -> None:
    profile = m15_facade_profile()
    dumped = profile.model_dump(mode="json")
    digest_payload = {key: value for key, value in dumped.items() if key != "facade_profile_digest"}

    assert profile.delegated_profile.profile_id == "kncc-gbm-longitudinal-concordance/1.0.0"
    assert profile.delegated_profile_digest == profile.delegated_profile.profile_digest
    assert profile.facade_profile_digest == sha256_digest(digest_payload)
    assert profile.output_semantics == "protein_level_longitudinal_source_concordance"
    assert profile.delegation.exact_request_passthrough is True
    assert profile.delegation.exact_result_passthrough is True
    assert profile.delegation.exact_replay_passthrough is True
    assert profile.claim_ceiling.supplies_source_cohort_longitudinal_protein_concordance is True
    assert profile.claim_ceiling.can_replace_synthetic_or_digest_derived_longitudinal_scores is True
    assert profile.claim_ceiling.uses_fitted_primary_recurrent_gbm_source_model is True
    assert profile.claim_ceiling.predicts_future_recurrence is False
    assert profile.claim_ceiling.predicts_outcome_or_survival is False
    assert profile.claim_ceiling.infers_clonal_evolution is False
    assert profile.claim_ceiling.infers_causal_mechanism is False
    assert profile.claim_ceiling.establishes_cross_cohort_validation is False
    assert profile.claim_ceiling.emits_clinical_class is False
    assert profile.claim_ceiling.recommends_treatment is False
    assert profile.claim_ceiling.governed_m15_replacement is False

    boundaries = {item.module_id: item for item in profile.responsibility_boundaries}
    assert set(boundaries) == {f"GLIO-PROTEOGEN-M15-{index:02d}" for index in range(1, 9)}
    assert all(item.module_responsibility_superseded is False for item in boundaries.values())
    assert (
        boundaries["GLIO-PROTEOGEN-M15-05"].disposition
        is M15ResponsibilityDisposition.LONGITUDINAL_EVIDENCE_SUBSTITUTION_ONLY
    )
    assert (
        boundaries["GLIO-PROTEOGEN-M15-03"].disposition is M15ResponsibilityDisposition.OUT_OF_SCOPE
    )
    assert (
        boundaries["GLIO-PROTEOGEN-M15-06"].disposition is M15ResponsibilityDisposition.OUT_OF_SCOPE
    )


def test_profile_rejects_incomplete_or_forged_content_bindings() -> None:
    profile = m15_facade_profile()

    with pytest.raises(ValidationError, match="complete and ordered"):
        M15LongitudinalRecurrenceFacadeProfile.model_validate(
            profile.model_copy(
                update={
                    "responsibility_boundaries": tuple(reversed(profile.responsibility_boundaries))
                }
            )
        )

    with pytest.raises(ValidationError, match="delegated profile digest"):
        M15LongitudinalRecurrenceFacadeProfile.model_validate(
            profile.model_copy(update={"delegated_profile_digest": "sha256:" + "0" * 64})
        )

    with pytest.raises(ValidationError, match="canonical profile content"):
        M15LongitudinalRecurrenceFacadeProfile.model_validate(
            profile.model_copy(update={"facade_profile_digest": "sha256:" + "f" * 64})
        )


def test_demo_analysis_and_replay_are_exact_delegations() -> None:
    request = m15_facade_demo()
    direct_result = analyze_longitudinal_gbm(request)
    facade_result = analyze_m15_longitudinal_recurrence_evidence(request)

    assert facade_result == direct_result
    assert facade_result.request_digest == request.request_digest
    assert facade_result.profile_digest == m15_facade_profile().delegated_profile_digest
    assert facade_result.result_digest == direct_result.result_digest

    envelope = ReplayVerificationRequest(request=request, result=facade_result)
    direct_replay = verify_longitudinal_gbm_replay(envelope)
    facade_replay = verify_m15_longitudinal_recurrence_replay(envelope)

    assert facade_replay == direct_replay
    assert facade_replay.verified is True
    assert facade_replay.recomputed_request_digest == request.request_digest
    assert facade_replay.recomputed_result_digest == facade_result.result_digest

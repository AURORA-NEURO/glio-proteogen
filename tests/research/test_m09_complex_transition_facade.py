"""Contract tests for the additive M09 participant-transition facade."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.longitudinal_gbm_complex_transition import (
    ComplexTransitionReplayVerificationRequest,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.m09_facade import (
    M09ComplexTransitionFacadeProfile,
    M09ResponsibilityDisposition,
    analyze_m09_complex_transition_evidence,
    m09_facade_demo,
    m09_facade_profile,
    verify_m09_complex_transition_replay,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.service import (
    analyze_longitudinal_gbm_complex_transition,
    verify_longitudinal_gbm_complex_transition_replay,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _run_bound_profile_validator(profile: M09ComplexTransitionFacadeProfile) -> None:
    validator = cast(
        "Callable[[], M09ComplexTransitionFacadeProfile]",
        profile.profile_is_complete_and_content_bound,
    )
    validator()


def test_profile_binds_exact_engine_complete_mapping_and_literal_claim_ceiling() -> None:
    profile = m09_facade_profile()
    dumped = profile.model_dump(mode="json")
    digest_payload = {key: value for key, value in dumped.items() if key != "facade_profile_digest"}

    assert profile.facade_profile_id == "m09-complex-transition-concordance-evidence/1.0.0"
    assert profile.route_prefix == "/v2/research/modules/m09/complex-transition-concordance"
    assert profile.delegated_profile.profile_id == "kncc-reactome-complex-transition/1.0.0"
    assert profile.delegated_profile_digest == profile.delegated_profile.profile_digest
    assert profile.facade_profile_digest == sha256_digest(digest_payload)
    assert profile.output_semantics == "reactome_participant_set_transition_concordance"
    assert profile.delegation.exact_request_passthrough is True
    assert profile.delegation.exact_result_passthrough is True
    assert profile.delegation.exact_replay_passthrough is True

    ceiling = profile.claim_ceiling
    assert ceiling.supplies_source_cohort_reactome_participant_set_transition_concordance is True
    assert ceiling.can_replace_synthetic_or_digest_derived_participant_transition_stand_ins is True
    assert ceiling.uses_fitted_primary_recurrent_gbm_source_model is True
    assert ceiling.infers_physical_complex_assembly is False
    assert ceiling.infers_stoichiometry is False
    assert ceiling.infers_essentiality is False
    assert ceiling.infers_complex_activity is False
    assert ceiling.infers_biochemical_activity is False
    assert ceiling.infers_causality is False
    assert ceiling.emits_prognosis is False
    assert ceiling.recommends_treatment is False
    assert ceiling.governed_m09_replacement is False

    boundaries = {item.module_id: item for item in profile.responsibility_boundaries}
    assert tuple(boundaries) == tuple(f"GLIO-PROTEOGEN-M09-{index:02d}" for index in range(1, 9))
    assert all(item.module_responsibility_superseded is False for item in boundaries.values())
    for module_id in (
        "GLIO-PROTEOGEN-M09-02",
        "GLIO-PROTEOGEN-M09-03",
        "GLIO-PROTEOGEN-M09-04",
    ):
        assert (
            boundaries[module_id].disposition
            is M09ResponsibilityDisposition.PARTICIPANT_TRANSITION_STAND_IN_SUBSTITUTION_ONLY
        )
    assert (
        boundaries["GLIO-PROTEOGEN-M09-05"].disposition is M09ResponsibilityDisposition.OUT_OF_SCOPE
    )


def test_facade_profile_rejects_resealed_reordered_or_forged_metadata() -> None:
    profile = m09_facade_profile()

    with pytest.raises(ValidationError, match="delegated profile digest"):
        M09ComplexTransitionFacadeProfile.model_validate(
            profile.model_copy(update={"delegated_profile_digest": "sha256:" + "0" * 64})
        )

    forged_delegated_profile = profile.delegated_profile.model_copy(
        update={"claim_ceiling": "forged_claim_ceiling"}
    )
    with pytest.raises(ValueError, match="exceeds the M09 facade claim ceiling"):
        _run_bound_profile_validator(
            profile.model_copy(update={"delegated_profile": forged_delegated_profile})
        )

    document = profile.model_dump(mode="json")
    document["responsibility_boundaries"] = list(reversed(document["responsibility_boundaries"]))
    payload = {key: value for key, value in document.items() if key != "facade_profile_digest"}
    document["facade_profile_digest"] = sha256_digest(payload)
    with pytest.raises(ValidationError, match="complete and ordered"):
        M09ComplexTransitionFacadeProfile.model_validate_json(
            json.dumps(document),
            strict=True,
        )

    document = profile.model_dump(mode="json")
    document["facade_profile_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValidationError, match="canonical profile content"):
        M09ComplexTransitionFacadeProfile.model_validate_json(
            json.dumps(document),
            strict=True,
        )


def test_demo_analysis_and_replay_are_exact_delegations() -> None:
    request = m09_facade_demo()
    direct_result = analyze_longitudinal_gbm_complex_transition(request)
    facade_result = analyze_m09_complex_transition_evidence(request)

    assert facade_result == direct_result
    assert facade_result.request_digest == request.request_digest
    assert facade_result.profile_digest == m09_facade_profile().delegated_profile_digest
    assert facade_result.result_digest == direct_result.result_digest

    envelope = ComplexTransitionReplayVerificationRequest(
        request=request,
        result=facade_result,
    )
    direct_replay = verify_longitudinal_gbm_complex_transition_replay(envelope)
    facade_replay = verify_m09_complex_transition_replay(envelope)

    assert facade_replay == direct_replay
    assert facade_replay.verified is True
    assert facade_replay.recomputed_request_digest == request.request_digest
    assert facade_replay.recomputed_result_digest == facade_result.result_digest

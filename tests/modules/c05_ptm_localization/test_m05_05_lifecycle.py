"""Lifecycle and safe-failure checks for M05-05 artifact detection."""

from __future__ import annotations

from typing import cast

import pytest
from evals.m05_05.run import build_scenario

from glio_proteogen.contracts.m05_05 import (
    DetectPtmLocalizationArtifactsRequest,
    PtmLocalizationArtifactDisposition,
    PtmLocalizationArtifactObservationState,
    PtmLocalizationArtifactPosteriorState,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection import (
    M0505Plugin,
    M0505Service,
    PtmLocalizationArtifactAuthorizationError,
    PtmLocalizationArtifactInputError,
    ValidatedM0505Request,
    detect_ptm_localization_artifacts,
)

_CASES = (
    "clear",
    "seeded_critical",
    "contamination_detected",
    "missing_required",
    "unsupported_required",
    "ledger_binding_only",
    "upstream_quarantined",
    "upstream_abstained",
)


@pytest.mark.parametrize("case_id", _CASES)
def test_genuine_m0503_scenarios_close_deterministically(case_id: str) -> None:
    scenario = build_scenario(case_id)

    first = detect_ptm_localization_artifacts(scenario.request)
    second = detect_ptm_localization_artifacts(scenario.request)

    assert first == second
    assert first.result_digest == second.result_digest
    assert first.disposition is scenario.expected_disposition
    assert len(first.artifact_posteriors) == scenario.expected_posteriors
    assert len(first.contamination_flags) == scenario.expected_flags
    assert len(first.exclusion_mask) == scenario.expected_exclusions
    assert first.request.raw_input_result == scenario.request.raw_input_result
    assert first.emits_variant_peptide is False
    assert first.emits_proteogenomic_state is False
    assert first.emits_proteotype is False
    assert first.emits_protein_level_subtype is False
    assert first.infers_kinase_activity is False
    assert first.recommends_treatment is False


def test_seeded_critical_event_detects_and_excludes_at_zero_fraction() -> None:
    result = detect_ptm_localization_artifacts(build_scenario("seeded_critical").request)
    detected = tuple(
        item
        for item in result.artifact_posteriors
        if item.state is PtmLocalizationArtifactPosteriorState.DETECTED
    )

    assert len(detected) == 1
    assert detected[0].posterior_ppm == 0
    assert result.disposition is PtmLocalizationArtifactDisposition.QUARANTINED
    assert len(result.exclusion_mask) == 1


def test_missing_evidence_remains_scoreless_and_abstains() -> None:
    result = detect_ptm_localization_artifacts(build_scenario("missing_required").request)
    missing = next(
        item
        for item in result.artifact_posteriors
        if item.observation_state is PtmLocalizationArtifactObservationState.MISSING
    )

    assert missing.state is PtmLocalizationArtifactPosteriorState.INDETERMINATE
    assert missing.posterior_ppm is None
    assert result.disposition is PtmLocalizationArtifactDisposition.ABSTAINED
    assert result.exclusion_mask == ()


def test_service_and_sealed_plugin_match_engine() -> None:
    request = build_scenario("contamination_detected").request
    service = M0505Service()
    plugin = M0505Plugin(service)

    expected = service.execute(request)
    token = plugin.validate(request)

    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M05-05"
    assert plugin.run(token) == expected
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("ValidatedM0505Request", object()))
    forged = ValidatedM0505Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)


def test_denied_control_fails_before_detection() -> None:
    request = build_scenario("clear").request
    references = request.context.references
    denied = references.consent.model_copy(update={"state": ConsentState.WITHHELD})
    context = request.context.model_copy(
        update={"references": references.model_copy(update={"consent": denied})}
    )
    candidate = request.model_copy(update={"context": context})

    with pytest.raises(PtmLocalizationArtifactAuthorizationError):
        detect_ptm_localization_artifacts(candidate)


def test_stale_m0503_result_digest_fails_strict_replay() -> None:
    request = build_scenario("clear").request
    forged_raw = request.raw_input_result.model_copy(
        update={"result_digest": "sha256:" + ("0" * 64)}
    )
    candidate = request.model_copy(update={"raw_input_result": forged_raw})

    with pytest.raises(PtmLocalizationArtifactInputError):
        detect_ptm_localization_artifacts(candidate)

    payload = request.model_dump(mode="python", exclude_none=False)
    payload["raw_input_result"] = forged_raw
    with pytest.raises(PtmLocalizationArtifactInputError):
        M0505Service.validate_request(cast("DetectPtmLocalizationArtifactsRequest", payload))

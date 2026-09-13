"""Boundary tests for the intentionally unmounted M07 cis-dosage facade."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.research.cptac_gbm_cis_dosage import (
    CisDosageEvidenceRequest,
    CisDosageEvidenceResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
)
from glio_proteogen.research.m07_copy_number_dosage_facade import (
    INTENDED_ROUTE_PREFIX,
    M07CisDosageFacadeProfile,
    M07ResponsibilityDisposition,
    analyze_m07_cis_dosage_cohort_evidence,
    m07_facade_profile,
    service,
    verify_m07_cis_dosage_cohort_replay,
)


def test_profile_maps_only_m07_04_to_exact_cohort_evidence_substitution() -> None:
    profile = m07_facade_profile()

    assert profile.facade_profile_digest == (
        "sha256:61d460e438bc01c2e9bbd290e929f744039e970ec99b8f62ab1a8bc61d53fbe1"
    )
    assert profile.delegated_profile_digest == profile.delegated_profile.profile_digest
    assert tuple(item.module_id for item in profile.responsibility_boundaries) == tuple(
        f"GLIO-PROTEOGEN-M07-{index:02d}" for index in range(1, 9)
    )
    substitutions = tuple(
        item.module_id
        for item in profile.responsibility_boundaries
        if item.disposition
        is M07ResponsibilityDisposition.COHORT_CIS_DOSAGE_EVIDENCE_SUBSTITUTION_ONLY
    )
    assert substitutions == ("GLIO-PROTEOGEN-M07-04",)
    assert (
        profile.responsibility_boundaries[4].disposition
        is M07ResponsibilityDisposition.OUT_OF_SCOPE
    )
    assert (
        profile.responsibility_boundaries[5].disposition
        is M07ResponsibilityDisposition.OUT_OF_SCOPE
    )
    assert all(
        not item.module_responsibility_superseded
        for item in profile.responsibility_boundaries
    )


def test_profile_structurally_proves_that_public_http_is_not_available() -> None:
    profile = m07_facade_profile()

    assert profile.intended_route_prefix == INTENDED_ROUTE_PREFIX
    assert profile.public_http_mounted is False
    assert profile.local_artifact_required is True
    assert profile.server_side_admitted_artifact_required_before_http is True
    assert profile.facade_runtime_state == "local_operator_artifact_only"
    assert profile.delegated_profile.public_http_mounted is False
    assert profile.delegation.redistribution_status == "local_only_terms_unverified"
    assert profile.claim_ceiling.accepts_patient_measurements is False
    assert profile.claim_ceiling.emits_patient_score is False
    assert profile.claim_ceiling.infers_individual_causal_mediation is False
    assert profile.claim_ceiling.governed_m07_replacement is False


def test_profile_rejects_a_forged_http_mount_or_m07_05_substitution() -> None:
    profile = m07_facade_profile()
    document = {
        name: getattr(profile, name)
        for name in M07CisDosageFacadeProfile.model_fields
    }
    document["public_http_mounted"] = True
    with pytest.raises(ValidationError):
        M07CisDosageFacadeProfile.model_validate(document)

    document = {
        name: getattr(profile, name)
        for name in M07CisDosageFacadeProfile.model_fields
    }
    boundaries = list(profile.responsibility_boundaries)
    boundaries[4] = boundaries[4].model_copy(
        update={
            "disposition": (
                M07ResponsibilityDisposition.COHORT_CIS_DOSAGE_EVIDENCE_SUBSTITUTION_ONLY
            )
        }
    )
    document["responsibility_boundaries"] = tuple(boundaries)
    document["facade_profile_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="only M07-04"):
        M07CisDosageFacadeProfile.model_validate(document)


def test_request_contract_contains_no_client_artifact_path() -> None:
    schema = CisDosageEvidenceRequest.model_json_schema()

    assert "artifact_path" not in schema["properties"]
    assert "operator_artifact_path" not in schema["properties"]


def test_local_analyze_wrapper_is_an_exact_delegate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = CisDosageEvidenceRequest(
        query_id="local-query",
        artifact_content_digest="sha256:" + "1" * 64,
        gene_symbols=("EGFR",),
    )
    path = Path("operator-selected-artifact.json")
    sentinel = cast("CisDosageEvidenceResult", object())

    def fake(
        observed: CisDosageEvidenceRequest,
        *,
        artifact_path: Path,
    ) -> CisDosageEvidenceResult:
        assert observed is request
        assert artifact_path == path
        return sentinel

    monkeypatch.setattr(service, "analyze_cis_dosage_evidence", fake)

    assert (
        analyze_m07_cis_dosage_cohort_evidence(request, operator_artifact_path=path)
        is sentinel
    )


def test_local_replay_wrapper_is_an_exact_delegate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verification = cast("ReplayVerificationRequest", object())
    path = Path("operator-selected-artifact.json")
    sentinel = cast("ReplayVerificationResult", object())

    def fake(
        observed: ReplayVerificationRequest,
        *,
        artifact_path: Path,
    ) -> ReplayVerificationResult:
        assert observed is verification
        assert artifact_path == path
        return sentinel

    monkeypatch.setattr(service, "verify_cis_dosage_replay", fake)

    assert (
        verify_m07_cis_dosage_cohort_replay(
            verification,
            operator_artifact_path=path,
        )
        is sentinel
    )

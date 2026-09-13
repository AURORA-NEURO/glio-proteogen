"""Strict M07 responsibility boundary for local CPTAC-GBM cis-dosage evidence."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, NonEmptyStr, Sha256Digest
from glio_proteogen.research.cptac_gbm_cis_dosage import CisDosageProfile  # noqa: TC001

FACADE_ID: Final = "m07-cptac-gbm-cis-dosage-cohort-evidence"
FACADE_VERSION: Final = "1.0.0"
FACADE_PROFILE_ID: Final = "m07-cptac-gbm-cis-dosage-cohort-evidence/1.0.0"
INTENDED_ROUTE_PREFIX: Final = "/v2/research/modules/m07/cis-dosage-cohort-evidence"

type M07ModuleId = Literal[
    "GLIO-PROTEOGEN-M07-01",
    "GLIO-PROTEOGEN-M07-02",
    "GLIO-PROTEOGEN-M07-03",
    "GLIO-PROTEOGEN-M07-04",
    "GLIO-PROTEOGEN-M07-05",
    "GLIO-PROTEOGEN-M07-06",
    "GLIO-PROTEOGEN-M07-07",
    "GLIO-PROTEOGEN-M07-08",
]


class M07ResponsibilityDisposition(StrEnum):
    """How local cohort evidence may relate to one provisional M07 duty."""

    COHORT_CIS_DOSAGE_EVIDENCE_SUBSTITUTION_ONLY = (
        "cohort_cis_dosage_evidence_substitution_only"
    )
    EVIDENCE_SOURCE_ONLY = "evidence_source_only"
    OUT_OF_SCOPE = "out_of_scope"


class M07ResponsibilityBoundary(FrozenModel):
    module_id: M07ModuleId
    responsibility: NonEmptyStr
    disposition: M07ResponsibilityDisposition
    module_responsibility_superseded: Literal[False] = False
    boundary: NonEmptyStr


class M07FacadeClaimCeiling(FrozenModel):
    supplies_source_locked_gbm_cohort_cis_dosage_evidence: Literal[True] = True
    can_substitute_m07_04_declaration_proxy_only: Literal[True] = True
    accepts_patient_measurements: Literal[False] = False
    emits_patient_score: Literal[False] = False
    emits_probabilistic_patient_posterior: Literal[False] = False
    infers_individual_causal_mediation: Literal[False] = False
    integrates_caller_mechanistic_constraints: Literal[False] = False
    establishes_external_calibration: Literal[False] = False
    recommends_treatment: Literal[False] = False
    governed_m07_replacement: Literal[False] = False


class M07FacadeDelegation(FrozenModel):
    engine_profile_id: Literal["cptac-gbm-cis-dosage/1.0.0"] = (
        "cptac-gbm-cis-dosage/1.0.0"
    )
    request_contract: Literal["CisDosageEvidenceRequest"] = "CisDosageEvidenceRequest"
    result_contract: Literal["CisDosageEvidenceResult"] = "CisDosageEvidenceResult"
    replay_request_contract: Literal["ReplayVerificationRequest"] = (
        "ReplayVerificationRequest"
    )
    replay_result_contract: Literal["ReplayVerificationResult"] = "ReplayVerificationResult"
    exact_request_passthrough: Literal[True] = True
    exact_result_passthrough: Literal[True] = True
    exact_replay_passthrough: Literal[True] = True
    local_operator_artifact_path_only: Literal[True] = True
    arbitrary_client_artifact_path_forbidden: Literal[True] = True
    redistribution_status: Literal["local_only_terms_unverified"] = (
        "local_only_terms_unverified"
    )


class M07CisDosageFacadeProfile(FrozenModel):
    facade_id: Literal["m07-cptac-gbm-cis-dosage-cohort-evidence"] = FACADE_ID
    facade_version: Literal["1.0.0"] = FACADE_VERSION
    facade_profile_id: Literal["m07-cptac-gbm-cis-dosage-cohort-evidence/1.0.0"] = (
        FACADE_PROFILE_ID
    )
    intended_route_prefix: Literal[
        "/v2/research/modules/m07/cis-dosage-cohort-evidence"
    ] = INTENDED_ROUTE_PREFIX
    public_http_mounted: Literal[False] = False
    local_artifact_required: Literal[True] = True
    server_side_admitted_artifact_required_before_http: Literal[True] = True
    facade_runtime_state: Literal["local_operator_artifact_only"] = (
        "local_operator_artifact_only"
    )
    delegation: M07FacadeDelegation
    claim_ceiling: M07FacadeClaimCeiling
    responsibility_boundaries: tuple[M07ResponsibilityBoundary, ...] = Field(
        min_length=8,
        max_length=8,
    )
    delegated_profile: CisDosageProfile
    delegated_profile_digest: Sha256Digest
    facade_profile_digest: Sha256Digest
    output_semantics: Literal["gbm_cohort_gene_cis_dosage_association_evidence"] = (
        "gbm_cohort_gene_cis_dosage_association_evidence"
    )
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def profile_is_content_bound_and_unmounted(self) -> Self:
        expected = tuple(f"GLIO-PROTEOGEN-M07-{index:02d}" for index in range(1, 9))
        observed = tuple(item.module_id for item in self.responsibility_boundaries)
        if observed != expected:
            raise ValueError("M07 responsibility boundaries must be complete and ordered")
        substitutions = tuple(
            item.module_id
            for item in self.responsibility_boundaries
            if item.disposition
            is M07ResponsibilityDisposition.COHORT_CIS_DOSAGE_EVIDENCE_SUBSTITUTION_ONLY
        )
        if substitutions != ("GLIO-PROTEOGEN-M07-04",):
            raise ValueError("only M07-04 may receive cohort cis-dosage substitution evidence")
        if self.delegated_profile_digest != self.delegated_profile.profile_digest:
            raise ValueError("delegated profile digest does not match the cis-dosage profile")
        if self.delegated_profile.public_http_mounted is not False:
            raise ValueError("local-only delegate unexpectedly permits public HTTP")
        payload = self.model_dump(mode="json", exclude={"facade_profile_digest"})
        if self.facade_profile_digest != sha256_digest(payload):
            raise ValueError("facade profile digest does not match canonical profile content")
        return self


__all__ = [
    "FACADE_ID",
    "FACADE_PROFILE_ID",
    "FACADE_VERSION",
    "INTENDED_ROUTE_PREFIX",
    "M07CisDosageFacadeProfile",
    "M07FacadeClaimCeiling",
    "M07FacadeDelegation",
    "M07ModuleId",
    "M07ResponsibilityBoundary",
    "M07ResponsibilityDisposition",
]

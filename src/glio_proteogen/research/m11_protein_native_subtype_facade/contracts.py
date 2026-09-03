"""Strict metadata for the M11-compatible published protein-axis facade."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, NonEmptyStr, Sha256Digest
from glio_proteogen.research.gbm_proteomic_axes import (  # noqa: TC001
    GbmProteomicAxesProfile,
)

FACADE_ID: Final = "m11-protein-native-subtype-protein-axis-evidence"
FACADE_VERSION: Final = "1.0.0"
FACADE_PROFILE_ID: Final = "m11-protein-native-subtype-protein-axis-evidence/1.0.0"
ROUTE_PREFIX: Final = "/v2/research/modules/m11/protein-native-subtype"

type M11ModuleId = Literal[
    "GLIO-PROTEOGEN-M11-01",
    "GLIO-PROTEOGEN-M11-02",
    "GLIO-PROTEOGEN-M11-03",
    "GLIO-PROTEOGEN-M11-04",
    "GLIO-PROTEOGEN-M11-05",
    "GLIO-PROTEOGEN-M11-06",
    "GLIO-PROTEOGEN-M11-07",
    "GLIO-PROTEOGEN-M11-08",
]


class M11ResponsibilityDisposition(StrEnum):
    """How the published axis receipt may relate to one provisional M11 duty."""

    AXIS_EVIDENCE_SUBSTITUTION_ONLY = "axis_evidence_substitution_only"
    EVIDENCE_SOURCE_ONLY = "evidence_source_only"
    OUT_OF_SCOPE = "out_of_scope"


class M11ResponsibilityBoundary(FrozenModel):
    """One conservative mapping from the evidence facade to an M11 responsibility."""

    module_id: M11ModuleId
    responsibility: NonEmptyStr
    disposition: M11ResponsibilityDisposition
    module_responsibility_superseded: Literal[False] = False
    boundary: NonEmptyStr


class M11FacadeClaimCeiling(FrozenModel):
    """Literal claim exclusions that callers can enforce without prose parsing."""

    supplies_published_protein_axis_evidence: Literal[True] = True
    can_replace_synthetic_or_caller_declared_axis_scores: Literal[True] = True
    emits_posterior_subtype_classifier: Literal[False] = False
    infers_longitudinal_evolution: Literal[False] = False
    emits_clinical_class: Literal[False] = False
    infers_mechanism: Literal[False] = False
    recommends_treatment: Literal[False] = False
    governed_m11_replacement: Literal[False] = False


class M11FacadeDelegation(FrozenModel):
    """Exact underlying contract and receipt identities used by the facade."""

    engine_profile_id: Literal["gbm-proteomic-axes/1.0.0"] = "gbm-proteomic-axes/1.0.0"
    request_contract: Literal["GbmProteomicAxesRequest"] = "GbmProteomicAxesRequest"
    result_contract: Literal["GbmProteomicAxesResult"] = "GbmProteomicAxesResult"
    replay_request_contract: Literal["GbmReplayVerificationRequest"] = (
        "GbmReplayVerificationRequest"
    )
    replay_result_contract: Literal["GbmReplayVerificationResult"] = "GbmReplayVerificationResult"
    exact_request_passthrough: Literal[True] = True
    exact_result_passthrough: Literal[True] = True
    exact_replay_passthrough: Literal[True] = True
    published_model_license: Literal["MIT"] = "MIT"


class M11ProteinNativeSubtypeFacadeProfile(FrozenModel):
    """Content-bound compatibility profile around the exact published model."""

    facade_id: Literal["m11-protein-native-subtype-protein-axis-evidence"] = FACADE_ID
    facade_version: Literal["1.0.0"] = FACADE_VERSION
    facade_profile_id: Literal["m11-protein-native-subtype-protein-axis-evidence/1.0.0"] = (
        FACADE_PROFILE_ID
    )
    route_prefix: Literal["/v2/research/modules/m11/protein-native-subtype"] = ROUTE_PREFIX
    delegation: M11FacadeDelegation
    claim_ceiling: M11FacadeClaimCeiling
    responsibility_boundaries: tuple[M11ResponsibilityBoundary, ...] = Field(
        min_length=8,
        max_length=8,
    )
    delegated_profile: GbmProteomicAxesProfile
    delegated_profile_digest: Sha256Digest
    facade_profile_digest: Sha256Digest
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def profile_is_content_bound(self) -> Self:
        identifiers = tuple(item.module_id for item in self.responsibility_boundaries)
        expected_identifiers = tuple(f"GLIO-PROTEOGEN-M11-{index:02d}" for index in range(1, 9))
        if identifiers != expected_identifiers:
            raise ValueError("M11 responsibility boundaries must be complete and ordered")
        if self.delegated_profile_digest != self.delegated_profile.profile_digest:
            raise ValueError("delegated profile digest does not match the published profile")
        payload = self.model_dump(mode="json", exclude={"facade_profile_digest"})
        if self.facade_profile_digest != sha256_digest(payload):
            raise ValueError("facade profile digest does not match canonical profile content")
        return self


__all__ = [
    "FACADE_ID",
    "FACADE_PROFILE_ID",
    "FACADE_VERSION",
    "ROUTE_PREFIX",
    "M11FacadeClaimCeiling",
    "M11FacadeDelegation",
    "M11ProteinNativeSubtypeFacadeProfile",
    "M11ResponsibilityBoundary",
    "M11ResponsibilityDisposition",
]

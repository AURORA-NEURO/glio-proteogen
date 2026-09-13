"""Strict metadata for the M14-compatible bulk protein-program facade."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, NonEmptyStr, Sha256Digest
from glio_proteogen.research.neftel_protein_programs import (  # noqa: TC001
    NeftelAlgorithmProfile,
)

FACADE_ID: Final = "m14-microenvironment-bulk-protein-program-evidence"
FACADE_VERSION: Final = "1.0.0"
FACADE_PROFILE_ID: Final = "m14-microenvironment-bulk-protein-program-evidence/1.0.0"
ROUTE_PREFIX: Final = "/v2/research/modules/m14/microenvironment-protein-programs"

type M14ModuleId = Literal[
    "GLIO-PROTEOGEN-M14-01",
    "GLIO-PROTEOGEN-M14-02",
    "GLIO-PROTEOGEN-M14-03",
    "GLIO-PROTEOGEN-M14-04",
    "GLIO-PROTEOGEN-M14-05",
    "GLIO-PROTEOGEN-M14-06",
    "GLIO-PROTEOGEN-M14-07",
    "GLIO-PROTEOGEN-M14-08",
]


class M14ResponsibilityDisposition(StrEnum):
    """How a bulk program receipt may relate to one provisional M14 duty."""

    PROGRAM_EVIDENCE_SUBSTITUTION_ONLY = "program_evidence_substitution_only"
    EVIDENCE_SOURCE_ONLY = "evidence_source_only"
    OUT_OF_SCOPE = "out_of_scope"


class M14ResponsibilityBoundary(FrozenModel):
    """One conservative mapping from the evidence facade to an M14 responsibility."""

    module_id: M14ModuleId
    responsibility: NonEmptyStr
    disposition: M14ResponsibilityDisposition
    module_responsibility_superseded: Literal[False] = False
    boundary: NonEmptyStr


class M14FacadeClaimCeiling(FrozenModel):
    """Literal exclusions preventing bulk concordance from becoming deconvolution."""

    supplies_bulk_protein_program_concordance: Literal[True] = True
    can_replace_synthetic_or_caller_declared_program_scores: Literal[True] = True
    emits_cell_fractions: Literal[False] = False
    performs_deconvolution: Literal[False] = False
    estimates_cell_abundance: Literal[False] = False
    emits_spatial_localization: Literal[False] = False
    infers_immune_composition: Literal[False] = False
    emits_clinical_class: Literal[False] = False
    recommends_treatment: Literal[False] = False
    governed_m14_replacement: Literal[False] = False


class M14FacadeDelegation(FrozenModel):
    """Exact underlying contract and receipt identities used by the facade."""

    engine_profile_id: Literal["neftel-bulk-protein-programs/1.0.0"] = (
        "neftel-bulk-protein-programs/1.0.0"
    )
    request_contract: Literal["ProteinProgramRequest"] = "ProteinProgramRequest"
    result_contract: Literal["ProteinProgramResult"] = "ProteinProgramResult"
    replay_request_contract: Literal["ReplayVerificationRequest"] = "ReplayVerificationRequest"
    replay_result_contract: Literal["ReplayVerificationResult"] = "ReplayVerificationResult"
    exact_request_passthrough: Literal[True] = True
    exact_result_passthrough: Literal[True] = True
    exact_replay_passthrough: Literal[True] = True


class M14MicroenvironmentProteinProgramsFacadeProfile(FrozenModel):
    """Content-bound M14 compatibility profile around the Neftel engine."""

    facade_id: Literal["m14-microenvironment-bulk-protein-program-evidence"] = FACADE_ID
    facade_version: Literal["1.0.0"] = FACADE_VERSION
    facade_profile_id: Literal["m14-microenvironment-bulk-protein-program-evidence/1.0.0"] = (
        FACADE_PROFILE_ID
    )
    route_prefix: Literal["/v2/research/modules/m14/microenvironment-protein-programs"] = (
        ROUTE_PREFIX
    )
    delegation: M14FacadeDelegation
    claim_ceiling: M14FacadeClaimCeiling
    responsibility_boundaries: tuple[M14ResponsibilityBoundary, ...] = Field(
        min_length=8,
        max_length=8,
    )
    delegated_profile: NeftelAlgorithmProfile
    delegated_profile_digest: Sha256Digest
    facade_profile_digest: Sha256Digest
    output_semantics: Literal["bulk_protein_program_evidence"] = "bulk_protein_program_evidence"
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def profile_is_content_bound(self) -> Self:
        identifiers = tuple(item.module_id for item in self.responsibility_boundaries)
        expected_identifiers = tuple(f"GLIO-PROTEOGEN-M14-{index:02d}" for index in range(1, 9))
        if identifiers != expected_identifiers:
            raise ValueError("M14 responsibility boundaries must be complete and ordered")
        if self.delegated_profile_digest != self.delegated_profile.profile_digest:
            raise ValueError("delegated profile digest does not match the Neftel profile")
        payload = self.model_dump(mode="json", exclude={"facade_profile_digest"})
        if self.facade_profile_digest != sha256_digest(payload):
            raise ValueError("facade profile digest does not match canonical profile content")
        return self


__all__ = [
    "FACADE_ID",
    "FACADE_PROFILE_ID",
    "FACADE_VERSION",
    "ROUTE_PREFIX",
    "M14FacadeClaimCeiling",
    "M14FacadeDelegation",
    "M14MicroenvironmentProteinProgramsFacadeProfile",
    "M14ResponsibilityBoundary",
    "M14ResponsibilityDisposition",
]

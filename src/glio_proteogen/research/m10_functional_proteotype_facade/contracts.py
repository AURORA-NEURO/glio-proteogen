"""Strict metadata for the M10-compatible functional-proteotype facade."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, NonEmptyStr, Sha256Digest
from glio_proteogen.research.gbm_functional_proteotype import (  # noqa: TC001
    FunctionalProteotypeProfile,
)

FACADE_ID: Final = "m10-functional-proteotype-evidence"
FACADE_VERSION: Final = "1.0.0"
FACADE_PROFILE_ID: Final = "m10-functional-proteotype-evidence/1.0.0"
ROUTE_PREFIX: Final = "/v2/research/modules/m10/functional-proteotype"

type M10ModuleId = Literal[
    "GLIO-PROTEOGEN-M10-01",
    "GLIO-PROTEOGEN-M10-02",
    "GLIO-PROTEOGEN-M10-03",
    "GLIO-PROTEOGEN-M10-04",
    "GLIO-PROTEOGEN-M10-05",
    "GLIO-PROTEOGEN-M10-06",
    "GLIO-PROTEOGEN-M10-07",
    "GLIO-PROTEOGEN-M10-08",
]


class M10ResponsibilityDisposition(StrEnum):
    """How the published receipt may relate to one provisional M10 duty."""

    RESEARCH_NUMERICAL_STAND_IN_SUBSTITUTION_ONLY = "research_numerical_stand_in_substitution_only"
    EVIDENCE_SOURCE_ONLY = "evidence_source_only"
    OUT_OF_SCOPE = "out_of_scope"


class M10ResponsibilityBoundary(FrozenModel):
    """One conservative mapping from the evidence facade to an M10 responsibility."""

    module_id: M10ModuleId
    responsibility: NonEmptyStr
    disposition: M10ResponsibilityDisposition
    module_responsibility_superseded: Literal[False] = False
    boundary: NonEmptyStr


class M10FacadeClaimCeiling(FrozenModel):
    """Literal exclusions preventing concordance evidence from becoming an M10 claim."""

    supplies_source_locked_four_axis_protein_concordance: Literal[True] = True
    can_replace_synthetic_or_caller_declared_m10_03_m10_07_numerical_stand_ins: Literal[True] = True
    emits_sample_pathway_activation: Literal[False] = False
    emits_posterior_subtype: Literal[False] = False
    infers_mechanism: Literal[False] = False
    infers_causal_perturbation: Literal[False] = False
    emits_prognosis: Literal[False] = False
    recommends_treatment: Literal[False] = False
    governed_m10_replacement: Literal[False] = False


class M10FacadeDelegation(FrozenModel):
    """Exact underlying contract and receipt identities used by the facade."""

    engine_profile_id: Literal["migliozzi-gbm-functional-proteotype/1.0.0"] = (
        "migliozzi-gbm-functional-proteotype/1.0.0"
    )
    request_contract: Literal["FunctionalProteotypeRequest"] = "FunctionalProteotypeRequest"
    result_contract: Literal["FunctionalProteotypeResult"] = "FunctionalProteotypeResult"
    replay_request_contract: Literal["ReplayVerificationRequest"] = "ReplayVerificationRequest"
    replay_result_contract: Literal["ReplayVerificationResult"] = "ReplayVerificationResult"
    exact_request_passthrough: Literal[True] = True
    exact_result_passthrough: Literal[True] = True
    exact_replay_passthrough: Literal[True] = True
    source_evidence_license: Literal["CC-BY-4.0"] = "CC-BY-4.0"


class M10FunctionalProteotypeFacadeProfile(FrozenModel):
    """Content-bound M10 compatibility profile around the exact research engine."""

    facade_id: Literal["m10-functional-proteotype-evidence"] = FACADE_ID
    facade_version: Literal["1.0.0"] = FACADE_VERSION
    facade_profile_id: Literal["m10-functional-proteotype-evidence/1.0.0"] = FACADE_PROFILE_ID
    route_prefix: Literal["/v2/research/modules/m10/functional-proteotype"] = ROUTE_PREFIX
    delegation: M10FacadeDelegation
    claim_ceiling: M10FacadeClaimCeiling
    responsibility_boundaries: tuple[M10ResponsibilityBoundary, ...] = Field(
        min_length=8,
        max_length=8,
    )
    delegated_profile: FunctionalProteotypeProfile
    delegated_profile_digest: Sha256Digest
    facade_profile_digest: Sha256Digest
    output_semantics: Literal["bulk_gbm_functional_proteotype_evidence"] = (
        "bulk_gbm_functional_proteotype_evidence"
    )
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def profile_is_content_bound(self) -> Self:
        identifiers = tuple(item.module_id for item in self.responsibility_boundaries)
        expected_identifiers = tuple(f"GLIO-PROTEOGEN-M10-{index:02d}" for index in range(1, 9))
        if identifiers != expected_identifiers:
            raise ValueError("M10 responsibility boundaries must be complete and ordered")
        if self.delegated_profile_digest != self.delegated_profile.profile_digest:
            raise ValueError("delegated profile digest does not match the Migliozzi profile")
        payload = self.model_dump(mode="json", exclude={"facade_profile_digest"})
        if self.facade_profile_digest != sha256_digest(payload):
            raise ValueError("facade profile digest does not match canonical profile content")
        return self


__all__ = [
    "FACADE_ID",
    "FACADE_PROFILE_ID",
    "FACADE_VERSION",
    "ROUTE_PREFIX",
    "M10FacadeClaimCeiling",
    "M10FacadeDelegation",
    "M10FunctionalProteotypeFacadeProfile",
    "M10ResponsibilityBoundary",
    "M10ResponsibilityDisposition",
]

"""M15 compatibility facade over fitted longitudinal GBM protein evidence.

The facade adds no numerical behavior.  It binds the exact KNCC/PDC000514
request, result, profile, and replay contracts to the eight provisional M15
responsibilities while keeping the governed ABI untouched.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import TYPE_CHECKING, Final, Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, NonEmptyStr, Sha256Digest

from .contracts import (
    LongitudinalGbmProfile,  # noqa: TC001 - Pydantic resolves the profile field at runtime.
    LongitudinalGbmRequest,  # noqa: TC001 - public facade annotations stay resolvable.
    LongitudinalGbmResult,  # noqa: TC001 - public facade annotations stay resolvable.
    ReplayVerificationRequest,  # noqa: TC001 - public facade annotations stay resolvable.
    ReplayVerificationResult,  # noqa: TC001 - public facade annotations stay resolvable.
)
from .demo import synthetic_demo_request
from .profile import algorithm_profile
from .service import analyze_longitudinal_gbm, verify_longitudinal_gbm_replay

if TYPE_CHECKING:
    from glio_proteogen.research.proteogenomic_state.cancellation import CancellationContext

FACADE_ID: Final = "m15-longitudinal-recurrence-protein-concordance-evidence"
FACADE_VERSION: Final = "1.0.0"
FACADE_PROFILE_ID: Final = "m15-longitudinal-recurrence-protein-concordance-evidence/1.0.0"
ROUTE_PREFIX: Final = "/v2/research/modules/m15/longitudinal-recurrence-proteotype"

type M15ModuleId = Literal[
    "GLIO-PROTEOGEN-M15-01",
    "GLIO-PROTEOGEN-M15-02",
    "GLIO-PROTEOGEN-M15-03",
    "GLIO-PROTEOGEN-M15-04",
    "GLIO-PROTEOGEN-M15-05",
    "GLIO-PROTEOGEN-M15-06",
    "GLIO-PROTEOGEN-M15-07",
    "GLIO-PROTEOGEN-M15-08",
]


class M15ResponsibilityDisposition(StrEnum):
    """How the fitted receipt may relate to one provisional M15 duty."""

    LONGITUDINAL_EVIDENCE_SUBSTITUTION_ONLY = "longitudinal_evidence_substitution_only"
    EVIDENCE_SOURCE_ONLY = "evidence_source_only"
    OUT_OF_SCOPE = "out_of_scope"


class M15ResponsibilityBoundary(FrozenModel):
    """One conservative mapping from fitted evidence to an M15 responsibility."""

    module_id: M15ModuleId
    responsibility: NonEmptyStr
    disposition: M15ResponsibilityDisposition
    module_responsibility_superseded: Literal[False] = False
    boundary: NonEmptyStr


class M15FacadeClaimCeiling(FrozenModel):
    """Literal exclusions that prevent concordance from becoming prognosis."""

    supplies_source_cohort_longitudinal_protein_concordance: Literal[True] = True
    can_replace_synthetic_or_digest_derived_longitudinal_scores: Literal[True] = True
    uses_fitted_primary_recurrent_gbm_source_model: Literal[True] = True
    predicts_future_recurrence: Literal[False] = False
    predicts_outcome_or_survival: Literal[False] = False
    infers_clonal_evolution: Literal[False] = False
    infers_causal_mechanism: Literal[False] = False
    establishes_cross_cohort_validation: Literal[False] = False
    emits_clinical_class: Literal[False] = False
    recommends_treatment: Literal[False] = False
    governed_m15_replacement: Literal[False] = False


class M15FacadeDelegation(FrozenModel):
    """Exact underlying contract and receipt identities used by the facade."""

    engine_profile_id: Literal["kncc-gbm-longitudinal-concordance/1.0.0"] = (
        "kncc-gbm-longitudinal-concordance/1.0.0"
    )
    request_contract: Literal["LongitudinalGbmRequest"] = "LongitudinalGbmRequest"
    result_contract: Literal["LongitudinalGbmResult"] = "LongitudinalGbmResult"
    replay_request_contract: Literal["ReplayVerificationRequest"] = "ReplayVerificationRequest"
    replay_result_contract: Literal["ReplayVerificationResult"] = "ReplayVerificationResult"
    exact_request_passthrough: Literal[True] = True
    exact_result_passthrough: Literal[True] = True
    exact_replay_passthrough: Literal[True] = True


class M15LongitudinalRecurrenceFacadeProfile(FrozenModel):
    """Content-bound compatibility profile around the fitted KNCC engine."""

    facade_id: Literal["m15-longitudinal-recurrence-protein-concordance-evidence"] = FACADE_ID
    facade_version: Literal["1.0.0"] = FACADE_VERSION
    facade_profile_id: Literal["m15-longitudinal-recurrence-protein-concordance-evidence/1.0.0"] = (
        FACADE_PROFILE_ID
    )
    route_prefix: Literal["/v2/research/modules/m15/longitudinal-recurrence-proteotype"] = (
        ROUTE_PREFIX
    )
    delegation: M15FacadeDelegation
    claim_ceiling: M15FacadeClaimCeiling
    responsibility_boundaries: tuple[M15ResponsibilityBoundary, ...] = Field(
        min_length=8,
        max_length=8,
    )
    delegated_profile: LongitudinalGbmProfile
    delegated_profile_digest: Sha256Digest
    facade_profile_digest: Sha256Digest
    output_semantics: Literal["protein_level_longitudinal_source_concordance"] = (
        "protein_level_longitudinal_source_concordance"
    )
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def profile_is_content_bound(self) -> Self:
        identifiers = tuple(item.module_id for item in self.responsibility_boundaries)
        expected = tuple(f"GLIO-PROTEOGEN-M15-{index:02d}" for index in range(1, 9))
        if identifiers != expected:
            raise ValueError("M15 responsibility boundaries must be complete and ordered")
        if self.delegated_profile_digest != self.delegated_profile.profile_digest:
            raise ValueError("delegated profile digest does not match the longitudinal profile")
        payload = self.model_dump(mode="json", exclude={"facade_profile_digest"})
        if self.facade_profile_digest != sha256_digest(payload):
            raise ValueError("facade profile digest does not match canonical profile content")
        return self


_RESPONSIBILITY_BOUNDARIES = (
    M15ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M15-01",
        responsibility="Biological hypothesis registry",
        disposition=M15ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The receipt may support a longitudinal hypothesis; it does not register, "
            "falsify, promote, or adjudicate one."
        ),
    ),
    M15ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M15-02",
        responsibility="Context and subtype stratification",
        disposition=M15ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The fitted coordinate is source-cohort transition evidence, not a subtype, "
            "disease stage, patient class, or clinical context assignment."
        ),
    ),
    M15ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M15-03",
        responsibility="Mechanistic feature construction",
        disposition=M15ResponsibilityDisposition.OUT_OF_SCOPE,
        boundary=(
            "The delegated engine consumes protein observations and does not construct "
            "causal, clonal, regulatory, spatial, treatment, or evolutionary features."
        ),
    ),
    M15ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M15-04",
        responsibility="Network, state, or mechanism inference",
        disposition=M15ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "Protein-transition concordance can be cited as evidence but is not a network "
            "state, pathway activity, causal mechanism, or evolutionary posterior."
        ),
    ),
    M15ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M15-05",
        responsibility="Longitudinal and evolutionary modeling",
        disposition=(M15ResponsibilityDisposition.LONGITUDINAL_EVIDENCE_SUBSTITUTION_ONLY),
        boundary=(
            "The fitted, uncertainty-bearing transition coordinate may replace only a "
            "synthetic, caller-declared, or digest-derived longitudinal score. It does not "
            "predict recurrence, infer clonal evolution, or supersede the M15 duty."
        ),
    ),
    M15ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M15-06",
        responsibility="Perturbation and sensitivity simulation",
        disposition=M15ResponsibilityDisposition.OUT_OF_SCOPE,
        boundary=(
            "Driver and source-processing ablations explain model sensitivity; they are "
            "not interventions, treatment effects, causal simulations, or counterfactuals."
        ),
    ),
    M15ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M15-07",
        responsibility="Plausibility and negative-control adjudication",
        disposition=M15ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The receipt exposes held-pair evaluation, support gates, uncertainty, and "
            "ablations but does not perform the complete governed adjudication workflow."
        ),
    ),
    M15ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M15-08",
        responsibility="Mechanism evidence dossier assembly",
        disposition=M15ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The replay-bound receipt may be referenced by a dossier; this facade does not "
            "assemble, promote, or govern an M15 evidence dossier."
        ),
    ),
)


@lru_cache(maxsize=1)
def m15_facade_profile() -> M15LongitudinalRecurrenceFacadeProfile:
    """Return the content-bound M15 compatibility and claim-ceiling profile."""

    delegated = algorithm_profile()
    payload = {
        "facade_id": FACADE_ID,
        "facade_version": FACADE_VERSION,
        "facade_profile_id": FACADE_PROFILE_ID,
        "route_prefix": ROUTE_PREFIX,
        "delegation": M15FacadeDelegation(),
        "claim_ceiling": M15FacadeClaimCeiling(),
        "responsibility_boundaries": _RESPONSIBILITY_BOUNDARIES,
        "delegated_profile": delegated,
        "delegated_profile_digest": delegated.profile_digest,
        "output_semantics": "protein_level_longitudinal_source_concordance",
        "research_use_only": True,
        "non_prescriptive": True,
    }
    return M15LongitudinalRecurrenceFacadeProfile.model_validate(
        {**payload, "facade_profile_digest": sha256_digest(payload)}
    )


def m15_facade_demo() -> LongitudinalGbmRequest:
    """Return the exact versioned synthetic request from the delegated service."""

    return synthetic_demo_request()


def analyze_m15_longitudinal_recurrence_evidence(
    request: LongitudinalGbmRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> LongitudinalGbmResult:
    """Delegate without changing request, result, or digest semantics."""

    return analyze_longitudinal_gbm(request, cancellation=cancellation)


def verify_m15_longitudinal_recurrence_replay(
    verification: ReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ReplayVerificationResult:
    """Delegate exact whole-receipt recomputation to the longitudinal service."""

    return verify_longitudinal_gbm_replay(verification, cancellation=cancellation)


__all__ = [
    "FACADE_ID",
    "FACADE_PROFILE_ID",
    "FACADE_VERSION",
    "ROUTE_PREFIX",
    "M15FacadeClaimCeiling",
    "M15FacadeDelegation",
    "M15LongitudinalRecurrenceFacadeProfile",
    "M15ResponsibilityBoundary",
    "M15ResponsibilityDisposition",
    "analyze_m15_longitudinal_recurrence_evidence",
    "m15_facade_demo",
    "m15_facade_profile",
    "verify_m15_longitudinal_recurrence_replay",
]

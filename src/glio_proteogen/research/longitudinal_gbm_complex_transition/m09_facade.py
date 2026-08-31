"""M09 compatibility facade over fitted Reactome participant transitions.

The facade adds no numerical behavior.  It binds the exact
``kncc-reactome-complex-transition/1.0.0`` request, result, profile, and replay
contracts to the eight provisional M09 responsibilities while keeping the
governed ABI untouched.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import TYPE_CHECKING, Final, Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, NonEmptyStr, Sha256Digest

from .contracts import (
    ComplexTransitionReplayVerificationRequest,  # noqa: TC001 - public annotations.
    ComplexTransitionReplayVerificationResult,  # noqa: TC001 - public annotations.
    LongitudinalGbmComplexTransitionProfile,  # noqa: TC001 - Pydantic runtime field.
    LongitudinalGbmComplexTransitionRequest,  # noqa: TC001 - public annotations.
    LongitudinalGbmComplexTransitionResult,  # noqa: TC001 - public annotations.
)
from .demo import synthetic_demo_request
from .profile import algorithm_profile
from .service import (
    analyze_longitudinal_gbm_complex_transition,
    verify_longitudinal_gbm_complex_transition_replay,
)

if TYPE_CHECKING:
    from glio_proteogen.research.proteogenomic_state.cancellation import CancellationContext

FACADE_ID: Final = "m09-complex-transition-concordance-evidence"
FACADE_VERSION: Final = "1.0.0"
FACADE_PROFILE_ID: Final = "m09-complex-transition-concordance-evidence/1.0.0"
ROUTE_PREFIX: Final = "/v2/research/modules/m09/complex-transition-concordance"

type M09ModuleId = Literal[
    "GLIO-PROTEOGEN-M09-01",
    "GLIO-PROTEOGEN-M09-02",
    "GLIO-PROTEOGEN-M09-03",
    "GLIO-PROTEOGEN-M09-04",
    "GLIO-PROTEOGEN-M09-05",
    "GLIO-PROTEOGEN-M09-06",
    "GLIO-PROTEOGEN-M09-07",
    "GLIO-PROTEOGEN-M09-08",
]


class M09ResponsibilityDisposition(StrEnum):
    """How participant-transition evidence may relate to one M09 duty."""

    PARTICIPANT_TRANSITION_STAND_IN_SUBSTITUTION_ONLY = (
        "participant_transition_stand_in_substitution_only"
    )
    EVIDENCE_SOURCE_ONLY = "evidence_source_only"
    OUT_OF_SCOPE = "out_of_scope"


class M09ResponsibilityBoundary(FrozenModel):
    """One conservative mapping from fitted evidence to an M09 responsibility."""

    module_id: M09ModuleId
    responsibility: NonEmptyStr
    disposition: M09ResponsibilityDisposition
    module_responsibility_superseded: Literal[False] = False
    boundary: NonEmptyStr


class M09FacadeClaimCeiling(FrozenModel):
    """Literal exclusions preventing concordance from becoming complex state."""

    supplies_source_cohort_reactome_participant_set_transition_concordance: Literal[True] = True
    can_replace_synthetic_or_digest_derived_participant_transition_stand_ins: Literal[True] = True
    uses_fitted_primary_recurrent_gbm_source_model: Literal[True] = True
    infers_physical_complex_assembly: Literal[False] = False
    infers_stoichiometry: Literal[False] = False
    infers_essentiality: Literal[False] = False
    infers_complex_activity: Literal[False] = False
    infers_biochemical_activity: Literal[False] = False
    infers_causality: Literal[False] = False
    emits_prognosis: Literal[False] = False
    recommends_treatment: Literal[False] = False
    governed_m09_replacement: Literal[False] = False


class M09FacadeDelegation(FrozenModel):
    """Exact delegated contract and receipt identities used by the facade."""

    engine_profile_id: Literal["kncc-reactome-complex-transition/1.0.0"] = (
        "kncc-reactome-complex-transition/1.0.0"
    )
    request_contract: Literal["LongitudinalGbmComplexTransitionRequest"] = (
        "LongitudinalGbmComplexTransitionRequest"
    )
    result_contract: Literal["LongitudinalGbmComplexTransitionResult"] = (
        "LongitudinalGbmComplexTransitionResult"
    )
    replay_request_contract: Literal["ComplexTransitionReplayVerificationRequest"] = (
        "ComplexTransitionReplayVerificationRequest"
    )
    replay_result_contract: Literal["ComplexTransitionReplayVerificationResult"] = (
        "ComplexTransitionReplayVerificationResult"
    )
    exact_request_passthrough: Literal[True] = True
    exact_result_passthrough: Literal[True] = True
    exact_replay_passthrough: Literal[True] = True


class M09ComplexTransitionFacadeProfile(FrozenModel):
    """Content-bound M09 compatibility profile around the exact fitted lane."""

    facade_id: Literal["m09-complex-transition-concordance-evidence"] = FACADE_ID
    facade_version: Literal["1.0.0"] = FACADE_VERSION
    facade_profile_id: Literal["m09-complex-transition-concordance-evidence/1.0.0"] = (
        FACADE_PROFILE_ID
    )
    route_prefix: Literal["/v2/research/modules/m09/complex-transition-concordance"] = ROUTE_PREFIX
    delegation: M09FacadeDelegation
    claim_ceiling: M09FacadeClaimCeiling
    responsibility_boundaries: tuple[M09ResponsibilityBoundary, ...] = Field(
        min_length=8,
        max_length=8,
    )
    delegated_profile: LongitudinalGbmComplexTransitionProfile
    delegated_profile_digest: Sha256Digest
    facade_profile_digest: Sha256Digest
    output_semantics: Literal["reactome_participant_set_transition_concordance"] = (
        "reactome_participant_set_transition_concordance"
    )
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def profile_is_complete_and_content_bound(self) -> Self:
        identifiers = tuple(item.module_id for item in self.responsibility_boundaries)
        expected = tuple(f"GLIO-PROTEOGEN-M09-{index:02d}" for index in range(1, 9))
        if identifiers != expected:
            raise ValueError("M09 responsibility boundaries must be complete and ordered")
        if self.delegated_profile_digest != self.delegated_profile.profile_digest:
            raise ValueError(
                "delegated profile digest does not match the complex-transition profile"
            )
        if self.delegated_profile.claim_ceiling != (
            "source_cohort_reactome_participant_set_transition_concordance_only"
        ):
            raise ValueError("delegated profile exceeds the M09 facade claim ceiling")
        payload = self.model_dump(mode="json", exclude={"facade_profile_digest"})
        if self.facade_profile_digest != sha256_digest(payload):
            raise ValueError("facade profile digest does not match canonical profile content")
        return self


_RESPONSIBILITY_BOUNDARIES = (
    M09ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M09-01",
        responsibility="Formal state and feature schema",
        disposition=M09ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The delegated request and receipt retain their own strict transition schema; "
            "they do not redefine, migrate, or supersede the governed M09-01 state model."
        ),
    ),
    M09ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M09-02",
        responsibility="Representation and feature constructor",
        disposition=(
            M09ResponsibilityDisposition.PARTICIPANT_TRANSITION_STAND_IN_SUBSTITUTION_ONLY
        ),
        boundary=(
            "Observed member transitions and fixed Reactome membership may replace only a "
            "synthetic or digest-derived participant-transition vector in research use. They "
            "are not a complex-state, assembly, stoichiometry, or activity representation."
        ),
    ),
    M09ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M09-03",
        responsibility="Mature baseline estimator",
        disposition=(
            M09ResponsibilityDisposition.PARTICIPANT_TRANSITION_STAND_IN_SUBSTITUTION_ONLY
        ),
        boundary=(
            "The fitted factor coordinate may replace only a synthetic, fixed, caller-declared, "
            "or digest-derived participant-set transition score. It is not a governed complex-"
            "activity or stoichiometry estimate and does not supersede M09-03."
        ),
    ),
    M09ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M09-04",
        responsibility="Probabilistic or advanced estimator",
        disposition=(
            M09ResponsibilityDisposition.PARTICIPANT_TRANSITION_STAND_IN_SUBSTITUTION_ONLY
        ),
        boundary=(
            "Robust rank-one projection and bootstrap uncertainty are usable only as fitted "
            "participant-transition evidence, not as physical assembly, essentiality, "
            "stoichiometry, biochemical activity, or a governed M09-04 posterior."
        ),
    ),
    M09ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M09-05",
        responsibility="Mechanism and constraint integrator",
        disposition=M09ResponsibilityDisposition.OUT_OF_SCOPE,
        boundary=(
            "Reactome participant membership is annotation, not a mechanistic constraint. The "
            "facade integrates no physical assembly, stoichiometric, essential-subunit, causal, "
            "or treatment constraint."
        ),
    ),
    M09ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M09-06",
        responsibility="Uncertainty decomposition engine",
        disposition=M09ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "Measurement and fitted-source intervals plus ablations are delegated diagnostics; "
            "they do not implement or supersede the governed M09-06 uncertainty taxonomy."
        ),
    ),
    M09ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M09-07",
        responsibility="Calibration and selective prediction",
        disposition=M09ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "Internal held-member evaluation and support gates may be cited as evidence, but "
            "they are not external calibration, selective clinical prediction, or prognosis."
        ),
    ),
    M09ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M09-08",
        responsibility="Evidence and explanation publisher",
        disposition=M09ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The replay-bound receipt may be referenced by an evidence bundle; this facade does "
            "not publish, promote, or govern an M09-08 explanation object."
        ),
    ),
)


@lru_cache(maxsize=1)
def m09_facade_profile() -> M09ComplexTransitionFacadeProfile:
    """Return the content-bound M09 responsibility and claim-ceiling profile."""

    delegated = algorithm_profile()
    payload = {
        "facade_id": FACADE_ID,
        "facade_version": FACADE_VERSION,
        "facade_profile_id": FACADE_PROFILE_ID,
        "route_prefix": ROUTE_PREFIX,
        "delegation": M09FacadeDelegation(),
        "claim_ceiling": M09FacadeClaimCeiling(),
        "responsibility_boundaries": _RESPONSIBILITY_BOUNDARIES,
        "delegated_profile": delegated,
        "delegated_profile_digest": delegated.profile_digest,
        "output_semantics": "reactome_participant_set_transition_concordance",
        "research_use_only": True,
        "non_prescriptive": True,
    }
    return M09ComplexTransitionFacadeProfile.model_validate(
        {**payload, "facade_profile_digest": sha256_digest(payload)}
    )


def m09_facade_demo() -> LongitudinalGbmComplexTransitionRequest:
    """Return the exact versioned synthetic request from the delegated service."""

    return synthetic_demo_request()


def analyze_m09_complex_transition_evidence(
    request: LongitudinalGbmComplexTransitionRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> LongitudinalGbmComplexTransitionResult:
    """Delegate without changing request, result, or digest semantics."""

    return analyze_longitudinal_gbm_complex_transition(request, cancellation=cancellation)


def verify_m09_complex_transition_replay(
    verification: ComplexTransitionReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ComplexTransitionReplayVerificationResult:
    """Delegate exact whole-receipt recomputation to the fitted service."""

    return verify_longitudinal_gbm_complex_transition_replay(
        verification,
        cancellation=cancellation,
    )


__all__ = [
    "FACADE_ID",
    "FACADE_PROFILE_ID",
    "FACADE_VERSION",
    "ROUTE_PREFIX",
    "M09ComplexTransitionFacadeProfile",
    "M09FacadeClaimCeiling",
    "M09FacadeDelegation",
    "M09ResponsibilityBoundary",
    "M09ResponsibilityDisposition",
    "analyze_m09_complex_transition_evidence",
    "m09_facade_demo",
    "m09_facade_profile",
    "verify_m09_complex_transition_replay",
]

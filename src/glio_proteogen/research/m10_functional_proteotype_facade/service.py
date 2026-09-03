"""Thin M10 facade over exact Migliozzi GBM functional-proteotype evidence."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbm_functional_proteotype import (
    FunctionalProteotypeRequest,
    FunctionalProteotypeResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
    algorithm_profile,
    analyze_functional_proteotype,
    synthetic_demo_request,
    verify_functional_proteotype_replay,
)

from .contracts import (
    M10FacadeClaimCeiling,
    M10FacadeDelegation,
    M10FunctionalProteotypeFacadeProfile,
    M10ResponsibilityBoundary,
    M10ResponsibilityDisposition,
)

if TYPE_CHECKING:
    from glio_proteogen.research.proteogenomic_state.cancellation import CancellationContext

_RESPONSIBILITY_BOUNDARIES = (
    M10ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M10-01",
        responsibility="Formal state and feature schema",
        disposition=M10ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The delegated request and receipt retain their own strict schema; they do not "
            "redefine, migrate, or supersede the governed M10-01 formal-state boundary."
        ),
    ),
    M10ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M10-02",
        responsibility="Representation and feature constructor",
        disposition=M10ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "Source-locked protein concordance may be cited as research evidence; this facade "
            "does not construct or supersede the governed M10-02 representation."
        ),
    ),
    M10ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M10-03",
        responsibility="Mature baseline estimator",
        disposition=(M10ResponsibilityDisposition.RESEARCH_NUMERICAL_STAND_IN_SUBSTITUTION_ONLY),
        boundary=(
            "The four source-locked protein-axis concordance estimates may replace only a "
            "synthetic or caller-declared numerical stand-in as research evidence; they are "
            "not a governed M10-03 baseline estimate or protein-RNA discordance result."
        ),
    ),
    M10ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M10-04",
        responsibility="Probabilistic or advanced estimator",
        disposition=M10ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "Robust axis concordance, intervals, and rank evidence may be consumed as research "
            "evidence; they are not a pathway-activation, subtype, or mechanism posterior and "
            "do not supersede M10-04."
        ),
    ),
    M10ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M10-05",
        responsibility="Mechanism and constraint integrator",
        disposition=M10ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The receipt may be referenced by an integrator, but the facade evaluates no "
            "mechanistic constraint and infers no mechanism or causal perturbation."
        ),
    ),
    M10ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M10-06",
        responsibility="Uncertainty decomposition engine",
        disposition=M10ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "Axis bootstrap intervals and ablations are delegated evidence diagnostics, not "
            "the governed M10-06 uncertainty taxonomy or decomposition."
        ),
    ),
    M10ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M10-07",
        responsibility="Calibration and selective prediction",
        disposition=(M10ResponsibilityDisposition.RESEARCH_NUMERICAL_STAND_IN_SUBSTITUTION_ONLY),
        boundary=(
            "Support-gated four-axis concordance may replace only a synthetic or "
            "caller-declared numerical stand-in as research evidence; it is not governed "
            "calibration, selective prediction, prognosis, or a clinical class."
        ),
    ),
    M10ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M10-08",
        responsibility="Evidence and explanation publisher",
        disposition=M10ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The replay-bound receipt may be referenced by an evidence bundle; this facade "
            "does not publish, promote, or govern an M10-08 explanation object."
        ),
    ),
)


@lru_cache(maxsize=1)
def m10_facade_profile() -> M10FunctionalProteotypeFacadeProfile:
    """Return the content-bound M10 compatibility and claim-ceiling profile."""

    delegated = algorithm_profile()
    payload = {
        "facade_id": "m10-functional-proteotype-evidence",
        "facade_version": "1.0.0",
        "facade_profile_id": "m10-functional-proteotype-evidence/1.0.0",
        "route_prefix": "/v2/research/modules/m10/functional-proteotype",
        "delegation": M10FacadeDelegation(),
        "claim_ceiling": M10FacadeClaimCeiling(),
        "responsibility_boundaries": _RESPONSIBILITY_BOUNDARIES,
        "delegated_profile": delegated,
        "delegated_profile_digest": delegated.profile_digest,
        "output_semantics": "bulk_gbm_functional_proteotype_evidence",
        "research_use_only": True,
        "non_prescriptive": True,
    }
    return M10FunctionalProteotypeFacadeProfile.model_validate(
        {**payload, "facade_profile_digest": sha256_digest(payload)}
    )


def m10_facade_demo() -> FunctionalProteotypeRequest:
    """Return the exact versioned synthetic request from the delegated service."""

    return synthetic_demo_request()


def analyze_m10_functional_proteotype_evidence(
    request: FunctionalProteotypeRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> FunctionalProteotypeResult:
    """Delegate without changing request, result, or digest semantics."""

    return analyze_functional_proteotype(request, cancellation=cancellation)


def verify_m10_functional_proteotype_replay(
    verification: ReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ReplayVerificationResult:
    """Delegate exact whole-receipt recomputation to the Migliozzi service."""

    return verify_functional_proteotype_replay(verification, cancellation=cancellation)


__all__ = [
    "analyze_m10_functional_proteotype_evidence",
    "m10_facade_demo",
    "m10_facade_profile",
    "verify_m10_functional_proteotype_replay",
]

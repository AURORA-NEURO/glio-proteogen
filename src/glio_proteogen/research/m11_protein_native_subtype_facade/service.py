"""Thin M11 evidence facade over the exact published GBM protein-axis service."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbm_proteomic_axes import (
    GbmProteomicAxesRequest,
    GbmProteomicAxesResult,
    GbmReplayVerificationRequest,
    GbmReplayVerificationResult,
    algorithm_profile,
    analyze_gbm_proteomic_axes,
    synthetic_demo_request,
    verify_gbm_proteomic_axes_replay,
)

from .contracts import (
    M11FacadeClaimCeiling,
    M11FacadeDelegation,
    M11ProteinNativeSubtypeFacadeProfile,
    M11ResponsibilityBoundary,
    M11ResponsibilityDisposition,
)

if TYPE_CHECKING:
    from glio_proteogen.research.proteogenomic_state.cancellation import CancellationContext

_RESPONSIBILITY_BOUNDARIES = (
    M11ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M11-01",
        responsibility="Biological hypothesis registry",
        disposition=M11ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary="The axis receipt may support a hypothesis; it does not register or adjudicate one.",
    ),
    M11ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M11-02",
        responsibility="Context and subtype stratification",
        disposition=M11ResponsibilityDisposition.AXIS_EVIDENCE_SUBSTITUTION_ONLY,
        boundary=(
            "Published continuous bulk-protein axis scores can replace only a synthetic or "
            "caller-declared axis-score placeholder; they do not map context or emit a "
            "posterior subtype classification."
        ),
    ),
    M11ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M11-03",
        responsibility="Mechanistic feature construction",
        disposition=M11ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The axis receipt may be cited as a source feature; it does not construct "
            "mechanistic, topology, lineage, kinetics, spatial, or regulatory features."
        ),
    ),
    M11ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M11-04",
        responsibility="Network, state, or mechanism inference",
        disposition=M11ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "Protein-axis scores are evidence, not a posterior mechanism, network state, "
            "causal effect, or kinase-activity estimate."
        ),
    ),
    M11ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M11-05",
        responsibility="Longitudinal and evolutionary modeling",
        disposition=M11ResponsibilityDisposition.OUT_OF_SCOPE,
        boundary=(
            "A single-sample axis score has no temporal model and cannot supersede trajectory "
            "or change-point responsibilities."
        ),
    ),
    M11ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M11-06",
        responsibility="Perturbation and sensitivity simulation",
        disposition=M11ResponsibilityDisposition.OUT_OF_SCOPE,
        boundary=(
            "The published predictor performs no intervention, parameter sweep, causal "
            "simulation, or treatment-effect estimation."
        ),
    ),
    M11ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M11-07",
        responsibility="Plausibility and negative-control adjudication",
        disposition=M11ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The receipt can be inspected as evidence but does not run orthogonal, negative, "
            "conservation, direction, or competing-mechanism controls."
        ),
    ),
    M11ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M11-08",
        responsibility="Mechanism evidence dossier assembly",
        disposition=M11ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The replay-bound receipt may be referenced by a dossier; this facade does not "
            "assemble, promote, or govern an M11 dossier."
        ),
    ),
)


@lru_cache(maxsize=1)
def m11_facade_profile() -> M11ProteinNativeSubtypeFacadeProfile:
    """Return the content-bound M11 compatibility and claim-ceiling profile."""

    delegated = algorithm_profile()
    payload = {
        "facade_id": "m11-protein-native-subtype-protein-axis-evidence",
        "facade_version": "1.0.0",
        "facade_profile_id": "m11-protein-native-subtype-protein-axis-evidence/1.0.0",
        "route_prefix": "/v2/research/modules/m11/protein-native-subtype",
        "delegation": M11FacadeDelegation(),
        "claim_ceiling": M11FacadeClaimCeiling(),
        "responsibility_boundaries": _RESPONSIBILITY_BOUNDARIES,
        "delegated_profile": delegated,
        "delegated_profile_digest": delegated.profile_digest,
        "research_use_only": True,
        "non_prescriptive": True,
    }
    return M11ProteinNativeSubtypeFacadeProfile.model_validate(
        {**payload, "facade_profile_digest": sha256_digest(payload)}
    )


def m11_facade_demo() -> GbmProteomicAxesRequest:
    """Return the exact versioned synthetic request from the delegated service."""

    return synthetic_demo_request()


def analyze_m11_protein_axis_evidence(
    request: GbmProteomicAxesRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> GbmProteomicAxesResult:
    """Delegate without changing request, result, or digest semantics."""

    return analyze_gbm_proteomic_axes(request, cancellation=cancellation)


def verify_m11_protein_axis_replay(
    verification: GbmReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> GbmReplayVerificationResult:
    """Delegate exact whole-receipt recomputation to the published-model service."""

    return verify_gbm_proteomic_axes_replay(verification, cancellation=cancellation)


__all__ = [
    "analyze_m11_protein_axis_evidence",
    "m11_facade_demo",
    "m11_facade_profile",
    "verify_m11_protein_axis_replay",
]

"""Thin M14 facade over exact Neftel bulk protein-program evidence."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.neftel_protein_programs import (
    ProteinProgramRequest,
    ProteinProgramResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
    algorithm_profile,
    analyze_neftel_protein_programs,
    synthetic_demo_request,
    verify_neftel_protein_program_replay,
)

from .contracts import (
    M14FacadeClaimCeiling,
    M14FacadeDelegation,
    M14MicroenvironmentProteinProgramsFacadeProfile,
    M14ResponsibilityBoundary,
    M14ResponsibilityDisposition,
)

if TYPE_CHECKING:
    from glio_proteogen.research.proteogenomic_state.cancellation import CancellationContext

_RESPONSIBILITY_BOUNDARIES = (
    M14ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M14-01",
        responsibility="Biological hypothesis registry",
        disposition=M14ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The program receipt may support a hypothesis; it does not register, falsify, "
            "or adjudicate one."
        ),
    ),
    M14ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M14-02",
        responsibility="Context and subtype stratification",
        disposition=M14ResponsibilityDisposition.PROGRAM_EVIDENCE_SUBSTITUTION_ONLY,
        boundary=(
            "Support-gated bulk protein-program scores can replace only a synthetic or "
            "caller-declared program-score placeholder; they do not map context, deconvolve "
            "cell populations, or emit a subtype or clinical class."
        ),
    ),
    M14ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M14-03",
        responsibility="Mechanistic feature construction",
        disposition=M14ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The program receipt may be cited as source evidence; it does not construct "
            "mechanistic, topology, lineage, kinetics, spatial, or regulatory features."
        ),
    ),
    M14ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M14-04",
        responsibility="Network, state, or mechanism inference",
        disposition=M14ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "Bulk program concordance is evidence, not a mechanism posterior, network state, "
            "causal effect, cell-of-origin assignment, or kinase-activity estimate."
        ),
    ),
    M14ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M14-05",
        responsibility="Longitudinal and evolutionary modeling",
        disposition=M14ResponsibilityDisposition.OUT_OF_SCOPE,
        boundary=(
            "A single-sample program receipt has no temporal model and cannot supersede "
            "trajectory, evolution, or change-point responsibilities."
        ),
    ),
    M14ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M14-06",
        responsibility="Perturbation and sensitivity simulation",
        disposition=M14ResponsibilityDisposition.OUT_OF_SCOPE,
        boundary=(
            "The delegated engine performs no intervention, parameter sweep, causal "
            "simulation, or treatment-effect estimation."
        ),
    ),
    M14ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M14-07",
        responsibility="Plausibility and negative-control adjudication",
        disposition=M14ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The receipt can be inspected as evidence but does not run orthogonal, negative, "
            "conservation, assay-physics, direction, or competing-mechanism controls."
        ),
    ),
    M14ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M14-08",
        responsibility="Mechanism evidence dossier assembly",
        disposition=M14ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The replay-bound receipt may be referenced by a dossier; this facade does not "
            "assemble, promote, or govern an M14 dossier."
        ),
    ),
)


@lru_cache(maxsize=1)
def m14_facade_profile() -> M14MicroenvironmentProteinProgramsFacadeProfile:
    """Return the content-bound M14 compatibility and claim-ceiling profile."""

    delegated = algorithm_profile()
    payload = {
        "facade_id": "m14-microenvironment-bulk-protein-program-evidence",
        "facade_version": "1.0.0",
        "facade_profile_id": "m14-microenvironment-bulk-protein-program-evidence/1.0.0",
        "route_prefix": "/v2/research/modules/m14/microenvironment-protein-programs",
        "delegation": M14FacadeDelegation(),
        "claim_ceiling": M14FacadeClaimCeiling(),
        "responsibility_boundaries": _RESPONSIBILITY_BOUNDARIES,
        "delegated_profile": delegated,
        "delegated_profile_digest": delegated.profile_digest,
        "output_semantics": "bulk_protein_program_evidence",
        "research_use_only": True,
        "non_prescriptive": True,
    }
    return M14MicroenvironmentProteinProgramsFacadeProfile.model_validate(
        {**payload, "facade_profile_digest": sha256_digest(payload)}
    )


def m14_facade_demo() -> ProteinProgramRequest:
    """Return the exact versioned synthetic request from the delegated service."""

    return synthetic_demo_request()


def analyze_m14_microenvironment_program_evidence(
    request: ProteinProgramRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ProteinProgramResult:
    """Delegate without changing request, result, or digest semantics."""

    return analyze_neftel_protein_programs(request, cancellation=cancellation)


def verify_m14_microenvironment_program_replay(
    verification: ReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ReplayVerificationResult:
    """Delegate exact whole-receipt recomputation to the Neftel service."""

    return verify_neftel_protein_program_replay(verification, cancellation=cancellation)


__all__ = [
    "analyze_m14_microenvironment_program_evidence",
    "m14_facade_demo",
    "m14_facade_profile",
    "verify_m14_microenvironment_program_replay",
]

"""Unmounted local M07 facade over exact CPTAC-GBM cis-dosage evidence."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.cptac_gbm_cis_dosage import (
    CisDosageEvidenceRequest,
    CisDosageEvidenceResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
    algorithm_profile,
    analyze_cis_dosage_evidence,
    verify_cis_dosage_replay,
)

from .contracts import (
    M07CisDosageFacadeProfile,
    M07FacadeClaimCeiling,
    M07FacadeDelegation,
    M07ResponsibilityBoundary,
    M07ResponsibilityDisposition,
)

_RESPONSIBILITY_BOUNDARIES = (
    M07ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M07-01",
        responsibility="Formal copy-number dosage state and feature schema",
        disposition=M07ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The exact gene-query receipt may be cited as research evidence but does not "
            "redefine or supersede the governed M07-01 state contract."
        ),
    ),
    M07ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M07-02",
        responsibility="Copy-number representation and feature constructor",
        disposition=M07ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "Exact HGNC mapping and fitted cohort coefficients are delegated evidence; this "
            "facade constructs no governed patient representation or learned embedding."
        ),
    ),
    M07ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M07-03",
        responsibility="Mature baseline estimator",
        disposition=M07ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "M07-03 already abstains without model authority. Cohort gene associations may "
            "inform later work but are not a patient baseline estimate and do not replace it."
        ),
    ),
    M07ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M07-04",
        responsibility="Probabilistic or advanced copy-number dosage estimator",
        disposition=(
            M07ResponsibilityDisposition.COHORT_CIS_DOSAGE_EVIDENCE_SUBSTITUTION_ONLY
        ),
        boundary=(
            "Fold-local Huber-IRLS CNV-to-RNA-to-protein cohort evidence may replace only the "
            "current scalar-copy or interval-midpoint declaration proxy. It is not an M07-04 "
            "patient posterior, individual effect, or governed estimator result."
        ),
    ),
    M07ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M07-05",
        responsibility="Mechanism and constraint integrator",
        disposition=M07ResponsibilityDisposition.OUT_OF_SCOPE,
        boundary=(
            "Observational propagated, buffered, or discordant cohort categories do not "
            "evaluate caller constraints, establish mechanism, or replace M07-05."
        ),
    ),
    M07ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M07-06",
        responsibility="Uncertainty decomposition engine",
        disposition=M07ResponsibilityDisposition.OUT_OF_SCOPE,
        boundary=(
            "Fold coefficients and held-out metrics are validation evidence, not the governed "
            "M07-06 uncertainty taxonomy or a patient uncertainty decomposition."
        ),
    ),
    M07ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M07-07",
        responsibility="Calibration and selective prediction",
        disposition=M07ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "Internal held-out gates and direction stability can support abstention decisions, "
            "but do not establish external calibration, transport, or clinical prediction."
        ),
    ),
    M07ResponsibilityBoundary(
        module_id="GLIO-PROTEOGEN-M07-08",
        responsibility="Evidence and explanation publisher",
        disposition=M07ResponsibilityDisposition.EVIDENCE_SOURCE_ONLY,
        boundary=(
            "The exact local replay receipt may be referenced by an evidence dossier; this "
            "facade does not publish or promote a governed M07-08 object."
        ),
    ),
)


@lru_cache(maxsize=1)
def m07_facade_profile() -> M07CisDosageFacadeProfile:
    """Return an exact, content-bound profile that proves HTTP is not mounted."""

    delegated = algorithm_profile()
    payload = {
        "facade_id": "m07-cptac-gbm-cis-dosage-cohort-evidence",
        "facade_version": "1.0.0",
        "facade_profile_id": "m07-cptac-gbm-cis-dosage-cohort-evidence/1.0.0",
        "intended_route_prefix": "/v2/research/modules/m07/cis-dosage-cohort-evidence",
        "public_http_mounted": False,
        "local_artifact_required": True,
        "server_side_admitted_artifact_required_before_http": True,
        "facade_runtime_state": "local_operator_artifact_only",
        "delegation": M07FacadeDelegation(),
        "claim_ceiling": M07FacadeClaimCeiling(),
        "responsibility_boundaries": _RESPONSIBILITY_BOUNDARIES,
        "delegated_profile": delegated,
        "delegated_profile_digest": delegated.profile_digest,
        "output_semantics": "gbm_cohort_gene_cis_dosage_association_evidence",
        "research_use_only": True,
        "non_prescriptive": True,
    }
    return M07CisDosageFacadeProfile.model_validate(
        {**payload, "facade_profile_digest": sha256_digest(payload)}
    )


def analyze_m07_cis_dosage_cohort_evidence(
    request: CisDosageEvidenceRequest,
    *,
    operator_artifact_path: Path,
) -> CisDosageEvidenceResult:
    """Delegate exactly to a same-user local artifact selected by the operator."""

    return analyze_cis_dosage_evidence(request, artifact_path=operator_artifact_path)


def verify_m07_cis_dosage_cohort_replay(
    verification: ReplayVerificationRequest,
    *,
    operator_artifact_path: Path,
) -> ReplayVerificationResult:
    """Replay the exact local receipt without translating it into an M07 posterior."""

    return verify_cis_dosage_replay(verification, artifact_path=operator_artifact_path)


__all__ = [
    "analyze_m07_cis_dosage_cohort_evidence",
    "m07_facade_profile",
    "verify_m07_cis_dosage_cohort_replay",
]

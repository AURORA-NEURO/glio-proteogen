"""Versioned, aggregate-only 240-iteration continuation of the legacy estimator.

The legacy model, profile, artifacts and biological labels remain unchanged.
This audit reuses pinned, pure legacy data-ordering and uncertainty helpers;
only fold-local Huber fits use the independently implemented iteration budget.
It deliberately keeps the legacy seed context for paired bootstrap comparisons.
No patient arrays are returned, and no legacy artifact can be promoted here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.resources import files
from typing import Final

import numpy as np
import numpy.typing as npt

from glio_proteogen.kernel.canonical import sha256_digest

from . import model as legacy
from .convergence import ALLOWED_ITERATION_BUDGETS
from .convergence_audit import BudgetPointRefit, refit_point_with_budget
from .model import BootstrapSummary, DiscordanceAggregateSummary, FoldFitTrace
from .profile import algorithm_profile

PROFILE_ID: Final = "cptac-gbm-transcript-protein-continuation/1.0.0"
ITERATION_BUDGET: Final = 240
BOOTSTRAP_REPLICATES: Final = 128
BOOTSTRAP_REQUIRED: Final = 103
COMPARISON_SEED_CONTEXT: Final = "cptac-gbm-transcript-protein-discordance|patient-bootstrap-v1"
_SOURCES: Final = ("convergence.py", "convergence_audit.py", "continuation.py")
_LIMITATIONS: Final = (
    "Explicit 240-iteration research continuation; the original 30-iteration estimator is unchanged.",
    "Internal held-out and patient-bootstrap diagnostics are not external validation.",
    "Paired draws retain the legacy request-digest seed context, independently of this profile ID.",
    "Nominal 90% bootstrap intervals are not multiplicity-adjusted or causally calibrated.",
    "No biological pattern label, patient prediction or legacy artifact promotion is provided.",
    "Convergence does not establish conditional-design identification or a clinical interpretation.",
)
FloatArray = npt.NDArray[np.float64]
FoldArray = npt.NDArray[np.int8]


@dataclass(frozen=True, slots=True)
class ContinuationGeneResult:
    """Aggregate receipt, including explicit failures and successful draw counts."""

    profile_id: str
    profile_digest: str
    budget: int
    comparison_request_digest: str
    comparison_bootstrap_seed: int
    comparison_seed_context: str
    accepted: bool
    point_valid_folds: int
    point_oof_patient_groups: int
    point_folds: tuple[FoldFitTrace, ...]
    bootstrap_requested: int
    bootstrap_attempted: int
    bootstrap_successful: int
    bootstrap_required: int
    summary: DiscordanceAggregateSummary | None
    failure_reason: str | None
    limitations: tuple[str, ...]


def continuation_profile_digest(*, budget: int = ITERATION_BUDGET) -> str:
    """Bind all continuation sources and the entire legacy semantic dependency."""

    profile = algorithm_profile()
    root = files(__package__)
    return sha256_digest(
        {
            "profile_id": PROFILE_ID,
            "iteration_budget": budget,
            "public_iteration_budget": ITERATION_BUDGET,
            "legacy_profile_digest": profile.profile_digest,
            "legacy_engine_semantic_digest": profile.engine_semantic_digest,
            "continuation_sources": {
                name: "sha256:"
                + hashlib.sha256(
                    root.joinpath(name).read_bytes().replace(b"\r\n", b"\n")
                ).hexdigest()
                for name in _SOURCES
            },
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_required": BOOTSTRAP_REQUIRED,
            "comparison_seed_context": COMPARISON_SEED_CONTEXT,
            "patient_arrays_returned": False,
            "legacy_artifact_promotion": False,
        }
    )


def _point(
    cnv: FloatArray,
    rna: FloatArray,
    protein: FloatArray,
    folds: FoldArray,
    *,
    budget: int,
) -> tuple[BudgetPointRefit, legacy._PointSummary | None]:
    refit = refit_point_with_budget(cnv, rna, protein, folds, max_iterations=budget)
    if not refit.accepted:
        return refit, None
    full, rna_only, cnv_only, null = refit.predictions
    cross_fit = legacy._CrossFit(
        observed=refit.observed,
        full=full,
        rna_only=rna_only,
        cnv_only=cnv_only,
        null=null,
        slopes=refit.raw_slopes,
        trace=refit.fold_trace,
    )
    return refit, legacy._point_summary(
        cross_fit,
        total=len(protein),
        complete=refit.complete_count,
    )


def _bootstrap(
    cnv: FloatArray,
    rna: FloatArray,
    protein: FloatArray,
    folds: FoldArray,
    *,
    point: legacy._PointSummary,
    request_digest: str,
    budget: int,
) -> tuple[int, BootstrapSummary | None]:
    seed = legacy._bootstrap_seed(request_digest)
    rng = np.random.default_rng(seed)
    tracks: tuple[list[float], ...] = tuple([] for _ in range(6))
    for _ in range(BOOTSTRAP_REPLICATES):
        indices = legacy._stratified_patient_bootstrap_indices(folds, rng)
        _, sampled = _point(
            cnv[indices], rna[indices], protein[indices], folds[indices], budget=budget
        )
        if sampled is None:
            continue
        values = (
            sampled.full.r2,
            sampled.delta_rna,
            sampled.delta_cnv,
            sampled.full.mae,
            sampled.full.residual_mad,
            sampled.slope_median,
        )
        for track, value in zip(tracks, values, strict=True):
            track.append(value)
    successful = len(tracks[0])
    if successful < BOOTSTRAP_REQUIRED:
        return successful, None
    full_r2, delta_rna, delta_cnv, mae, residual_mad, slopes = tracks
    return successful, BootstrapSummary(
        seed=seed,
        replicates_requested=BOOTSTRAP_REPLICATES,
        replicates_successful=successful,
        full_model_r2=legacy._finite_sample_interval(full_r2, point.full.r2),
        delta_r2_vs_rna_only=legacy._finite_sample_interval(
            delta_rna,
            legacy._quantized_difference(point.full.r2, point.rna_only.r2),
        ),
        delta_r2_vs_cnv_only=legacy._finite_sample_interval(
            delta_cnv,
            legacy._quantized_difference(point.full.r2, point.cnv_only.r2),
        ),
        full_model_mae=legacy._finite_sample_interval(mae, point.full.mae),
        full_model_residual_mad=legacy._finite_sample_interval(
            residual_mad, point.full.residual_mad
        ),
        conditional_rna_slope=legacy._finite_sample_interval(slopes, point.slope_median),
    )


def _fit_continuation_gene_for_budget(
    cnv: legacy.InputFloatArray,
    rna: legacy.InputFloatArray,
    protein: legacy.InputFloatArray,
    folds: FoldArray,
    *,
    request_digest: str,
    budget: int,
) -> ContinuationGeneResult:
    """Private lower-budget oracle; public continuation always uses exactly 240."""

    if type(budget) is not int:
        raise TypeError("budget must be an exact integer")
    if budget not in ALLOWED_ITERATION_BUDGETS:
        raise ValueError("audit budget must be one of 30, 60, 120, or 240")
    digest = legacy._validate_request_digest(request_digest)
    configuration = legacy.DiscordanceFitConfiguration()
    arrays = legacy._validate_inputs(cnv, rna, protein, folds, configuration)
    order = legacy._canonical_row_order(*arrays)
    validated_cnv, validated_rna, validated_protein, validated_folds = arrays
    canonical_cnv = validated_cnv[order]
    canonical_rna = validated_rna[order]
    canonical_protein = validated_protein[order]
    canonical_folds = validated_folds[order]
    refit, point = _point(
        canonical_cnv,
        canonical_rna,
        canonical_protein,
        canonical_folds,
        budget=budget,
    )
    attempted = successful = 0
    summary = None
    failure: str | None = "point fit failed the unchanged fold/OOF/finite-metric support gates"
    if point is not None:
        attempted = BOOTSTRAP_REPLICATES
        successful, bootstrap = _bootstrap(
            canonical_cnv,
            canonical_rna,
            canonical_protein,
            canonical_folds,
            point=point,
            request_digest=digest,
            budget=budget,
        )
        if bootstrap is None:
            failure = "fewer than 103 of 128 stratified patient-bootstrap replicates passed"
        else:
            summary = legacy._aggregate_summary(point, bootstrap)
            failure = None
    return ContinuationGeneResult(
        profile_id=PROFILE_ID,
        profile_digest=continuation_profile_digest(budget=budget),
        budget=budget,
        comparison_request_digest=digest,
        comparison_bootstrap_seed=legacy._bootstrap_seed(digest),
        comparison_seed_context=COMPARISON_SEED_CONTEXT,
        accepted=summary is not None,
        point_valid_folds=refit.valid_folds,
        point_oof_patient_groups=refit.oof_count,
        point_folds=refit.fold_trace,
        bootstrap_requested=BOOTSTRAP_REPLICATES,
        bootstrap_attempted=attempted,
        bootstrap_successful=successful,
        bootstrap_required=BOOTSTRAP_REQUIRED,
        summary=summary,
        failure_reason=failure,
        limitations=_LIMITATIONS,
    )


def fit_continuation_gene(
    cnv: legacy.InputFloatArray,
    rna: legacy.InputFloatArray,
    protein: legacy.InputFloatArray,
    folds: FoldArray,
    *,
    request_digest: str,
    budget: int = ITERATION_BUDGET,
) -> ContinuationGeneResult:
    """Run the fixed 240-iteration continuation and return only aggregate evidence."""

    if type(budget) is not int:
        raise TypeError("budget must be an exact integer")
    if budget != ITERATION_BUDGET:
        raise ValueError("the public continuation profile requires budget=240")
    return _fit_continuation_gene_for_budget(
        cnv,
        rna,
        protein,
        folds,
        request_digest=request_digest,
        budget=budget,
    )


__all__ = [
    "BOOTSTRAP_REPLICATES",
    "BOOTSTRAP_REQUIRED",
    "ITERATION_BUDGET",
    "PROFILE_ID",
    "ContinuationGeneResult",
    "continuation_profile_digest",
    "fit_continuation_gene",
]

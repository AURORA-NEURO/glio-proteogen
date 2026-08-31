# ruff: noqa: PLR0915, PLR2004, T201, TRY003
"""Fit the de-identified KNCC Reactome conditional-transition model.

This source-locked offline fitter consumes the verified PDC000514 paired protein
matrix and the already admitted Reactome source catalog.  Patient measurements,
identifiers, hashes, scores, residuals, fold assignments, and bootstrap resample
indices are never serialized.  Only aggregate evaluation and fitted coefficients
are emitted.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple, cast

import numpy as np
import numpy.typing as npt

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.research.longitudinal_gbm_reactome_transition.catalog import (
    PROFILE_ID,
    ReactomeTransitionSourceCatalog,
    reactome_transition_source_catalog,
)
from tools import import_kncc_longitudinal_gbm as base

MODEL_ID: Final = "kncc-reactome-conditional-transition-model/1.0.0"
SCHEMA_VERSION: Final = (
    "glio-proteogen.kncc-reactome-conditional-transition-model/1.0.0"
)
ARTIFACT_ROLE: Final = (
    "de-identified fitted conditional protein-transition concordance model"
)
PRIMARY_MEASURE: Final = "Unshared Log"
SOURCE_PROCESSING_ABLATION_MEASURE: Final = "Log"
OUTER_FOLDS: Final = 8
GENE_FOLDS: Final = 5
OUTER_FOLD_SALT: Final = "kncc-reactome-panel-outer-v1"
GENE_FOLD_SALT: Final = "kncc-reactome-gene-fold-v1"
HUBER_K: Final = 1.345
RIDGE_LAMBDA: Final = 1.0
GLOBAL_RIDGE_MULTIPLIER: Final = 0.25
SOLVER_DAMPING: Final = 0.7
SOLVER_MAX_ITERATIONS: Final = 200
SOLVER_TOLERANCE: Final = 1.0e-9
DEFAULT_BOOTSTRAP_REPLICATES: Final = 256
PATIENT_BOOTSTRAP_REPLICATES: Final = 20_000
PATIENT_BOOTSTRAP_SEED: Final = 20_260_830
QUANTIZATION_DECIMALS: Final = 10

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class DesignInputs:
    """Fixed topology needed to derive the fitted loading dictionary."""

    union_indices: IntArray
    local_by_feature: dict[int, int]
    degree: FloatArray
    members_by_pathway: tuple[IntArray, ...]


@dataclass(frozen=True, slots=True)
class FitView:
    """Minimal view of a source fit used by this importer."""

    scale: FloatArray
    support: IntArray
    eligible: npt.NDArray[np.bool_]
    effect: FloatArray
    order: IntArray
    intensity_floor: float
    iterations: int
    converged: bool


class SolveOutcome(NamedTuple):
    coordinates: FloatArray
    iterations: int
    converged: bool
    final_max_change: float


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _raw_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _q(value: float) -> float:
    result = round(float(value), QUANTIZATION_DECIMALS)
    return 0.0 if result == 0.0 else result


def _tensor(value: npt.NDArray[np.generic], dtype: str) -> dict[str, object]:
    array = np.ascontiguousarray(value, dtype=np.dtype(dtype))
    payload = array.tobytes(order="C")
    compressed = zlib.compress(payload, level=9)
    return {
        "dtype": dtype,
        "shape": list(array.shape),
        "encoding": "base64+zlib",
        "raw_bytes": len(payload),
        "raw_sha256": _raw_digest(payload),
        "data": base64.b64encode(compressed).decode("ascii"),
    }


def _recipe() -> dict[str, object]:
    return {
        "input_transition": "paired recurrent T2 minus primary T1 protein abundance",
        "primary_measure": PRIMARY_MEASURE,
        "source_processing_ablation_measure": SOURCE_PROCESSING_ABLATION_MEASURE,
        "training_coverage_minimum": base.MIN_TRAIN_COVERAGE,
        "mad_consistency_constant": 1.4826,
        "intensity_floor_quantile": base.INTENSITY_FLOOR_QUANTILE,
        "minimum_intensity_floor": base.MIN_INTENSITY_FLOOR,
        "location_huber_k": base.HUBER_K,
        "location_max_iterations": base.HUBER_MAX_ITERATIONS,
        "location_tolerance": base.HUBER_TOLERANCE,
        "outer_folds": OUTER_FOLDS,
        "held_gene_folds": GENE_FOLDS,
        "outer_fold_salt": OUTER_FOLD_SALT,
        "gene_fold_salt": GENE_FOLD_SALT,
        "pathway_shared_gene_weight": "inverse square root of panel-membership degree",
        "pathway_adjustment": "orthogonal projection against fitted global loading",
        "loading_l2_norm": 1.0,
        "design_row_scale": "square root of union feature count",
        "solver_huber_k": HUBER_K,
        "solver_ridge_lambda": RIDGE_LAMBDA,
        "solver_global_ridge_multiplier": GLOBAL_RIDGE_MULTIPLIER,
        "solver_damping": SOLVER_DAMPING,
        "solver_max_iterations": SOLVER_MAX_ITERATIONS,
        "solver_tolerance": SOLVER_TOLERANCE,
        "bootstrap_generator": "numpy.random.Generator(PCG64)",
        "bootstrap_seed_policy": (
            "first 64 SHA-256 bits of source-content-digest, recipe-digest, and "
            "zero-based replicate index"
        ),
        "bootstrap_resample_unit": "strict paired patient group",
        "coefficient_storage": "little-endian float32 bootstrap tensors",
        "reference_storage": "little-endian float64 tensors",
        "quantization_decimals": QUANTIZATION_DECIMALS,
        "claim_ceiling": "conditional source-cohort protein-transition concordance only",
    }


def _design_inputs(source: ReactomeTransitionSourceCatalog) -> DesignInputs:
    union = np.asarray(
        sorted(
            set().union(
                *(set(pathway.member_feature_indices) for pathway in source.pathways)
            )
        ),
        dtype=np.int64,
    )
    local = {int(feature): index for index, feature in enumerate(union)}
    degree = np.zeros(union.size, dtype=np.float64)
    members: list[IntArray] = []
    for pathway in source.pathways:
        positions = np.asarray(
            [local[index] for index in pathway.member_feature_indices],
            dtype=np.int64,
        )
        members.append(positions)
        degree[positions] += 1.0
    if union.size == 0 or np.any(degree < 1.0):
        raise ValueError("Reactome fitted union is empty or has invalid membership degree")
    return DesignInputs(
        union_indices=union,
        local_by_feature=local,
        degree=degree,
        members_by_pathway=tuple(members),
    )


def _view(fit: base.AxisFit) -> FitView:
    return FitView(
        scale=fit.scale,
        support=fit.support,
        eligible=fit.eligible,
        effect=fit.effect,
        order=fit.order,
        intensity_floor=fit.intensity_floor,
        iterations=fit.iterations,
        converged=fit.converged,
    )


def _design(
    fit: FitView,
    inputs: DesignInputs,
    *,
    degree_normalization: bool = True,
) -> FloatArray:
    effect = fit.effect[inputs.union_indices]
    global_norm = float(np.linalg.norm(effect))
    if not math.isfinite(global_norm) or global_norm <= 0.0:
        raise ValueError("global recurrence loading has zero or non-finite norm")
    global_loading = effect / global_norm
    columns: list[FloatArray] = [global_loading]
    for member_positions in inputs.members_by_pathway:
        raw = np.zeros(inputs.union_indices.size, dtype=np.float64)
        feature_indices = inputs.union_indices[member_positions]
        active = fit.eligible[feature_indices]
        positions = member_positions[active]
        divisor = np.sqrt(inputs.degree[positions]) if degree_normalization else 1.0
        raw[positions] = effect[positions] / divisor
        projection = float(np.dot(global_loading, raw))
        raw -= global_loading * projection
        norm = float(np.linalg.norm(raw))
        if not math.isfinite(norm) or norm <= 0.0:
            raise ValueError("conditional pathway loading has zero or non-finite norm")
        columns.append(raw / norm)
    return np.column_stack(columns) * math.sqrt(inputs.union_indices.size)


def _solve(design: FloatArray, values: FloatArray) -> SolveOutcome:
    coordinates = np.zeros(design.shape[1], dtype=np.float64)
    penalty = np.eye(design.shape[1], dtype=np.float64)
    penalty[0, 0] = GLOBAL_RIDGE_MULTIPLIER
    for iteration in range(1, SOLVER_MAX_ITERATIONS + 1):
        residual = values - design @ coordinates
        weights = np.minimum(
            1.0,
            HUBER_K / np.maximum(np.abs(residual), 1.0e-12),
        )
        system = design.T @ (weights[:, None] * design) + RIDGE_LAMBDA * penalty
        target = design.T @ (weights * values)
        updated = np.linalg.solve(system, target)
        if float(np.max(np.abs(updated - coordinates))) < SOLVER_TOLERANCE:
            return SolveOutcome(
                coordinates=updated,
                iterations=iteration,
                converged=True,
                final_max_change=float(np.max(np.abs(updated - coordinates))),
            )
        coordinates = SOLVER_DAMPING * updated + (1.0 - SOLVER_DAMPING) * coordinates
    return SolveOutcome(
        coordinates=coordinates,
        iterations=SOLVER_MAX_ITERATIONS,
        converged=False,
        final_max_change=float(np.max(np.abs(updated - coordinates))),
    )


def _gene_fold(genes: tuple[str, ...], feature_indices: IntArray) -> IntArray:
    return np.asarray(
        [
            int.from_bytes(
                hashlib.sha256(
                    f"{GENE_FOLD_SALT}:{genes[int(index)]}".encode()
                ).digest()[:2],
                "big",
            )
            % GENE_FOLDS
            for index in feature_indices
        ],
        dtype=np.int64,
    )


def _relative_improvement(reference: float, candidate: float) -> float:
    return (reference - candidate) / reference if reference > 0.0 else 0.0


def _loading_cosines(left: FloatArray, right: FloatArray) -> FloatArray:
    numerator = np.sum(left * right, axis=0)
    denominator = np.linalg.norm(left, axis=0) * np.linalg.norm(right, axis=0)
    return numerator / denominator


def _spearman(values: FloatArray) -> FloatArray:
    ranks = np.empty_like(values)
    for column in range(values.shape[1]):
        order = np.argsort(values[:, column], kind="mergesort")
        ranks[order, column] = np.arange(values.shape[0], dtype=np.float64)
    return cast("FloatArray", np.corrcoef(ranks, rowvar=False))


def _naive_score(
    delta: FloatArray,
    fit: FitView,
    indices: IntArray,
) -> FloatArray:
    eligible = indices[fit.eligible[indices]]
    effect = fit.effect[eligible]
    norm = float(np.abs(effect).sum())
    if norm <= 0.0:
        return np.full(delta.shape[0], np.nan, dtype=np.float64)
    weights = effect / norm
    return base._project(delta, fit.scale, eligible, weights)[0]


def _evaluation(
    cohort: base.Cohort,
    source: ReactomeTransitionSourceCatalog,
    inputs: DesignInputs,
    reference_design: FloatArray,
) -> tuple[dict[str, object], FloatArray]:
    folds = base._folds(cohort.patient_groups, OUTER_FOLDS, OUTER_FOLD_SALT)
    all_indices = np.arange(len(cohort.patient_groups), dtype=np.int64)
    gene_folds = _gene_fold(cohort.genes, inputs.union_indices)
    zero_errors: list[float] = []
    global_errors: list[float] = []
    joint_errors: list[float] = []
    global_rmse: list[float] = []
    joint_rmse: list[float] = []
    per_patient_improvements = np.empty(
        (len(cohort.patient_groups), GENE_FOLDS), dtype=np.float64
    )
    removal_penalties: list[list[float]] = [[] for _ in source.pathways]
    conditions: list[float] = []
    fold_cosines: list[FloatArray] = []
    oof_coordinates = np.empty(
        (len(cohort.patient_groups), 1 + len(source.pathways)), dtype=np.float64
    )
    naive_scores = np.empty(
        (len(cohort.patient_groups), 1 + len(source.pathways)), dtype=np.float64
    )
    iteration_counts: list[int] = []
    nonconverged_by_role = {
        "full_patient": 0,
        "global_held_gene": 0,
        "joint_held_gene": 0,
        "leave_pathway_out": 0,
    }
    maximum_final_change_by_role = dict.fromkeys(nonconverged_by_role, 0.0)
    minimum_finite_held_gene_count = inputs.union_indices.size
    minimum_finite_inference_gene_count = inputs.union_indices.size
    for held in folds:
        train = np.setdiff1d(all_indices, held, assume_unique=True)
        fit = _view(base._fit_axis(cohort.primary_delta[train], cohort.genes))
        design = _design(fit, inputs)
        conditions.append(float(np.linalg.cond(design)))
        fold_cosines.append(_loading_cosines(design, reference_design))
        scale = fit.scale[inputs.union_indices]
        global_indices, global_weights = base._weights(
            cast("base.AxisFit", fit),  # compatible structural fields
            256,
        )
        naive_scores[held, 0] = base._project(
            cohort.primary_delta[held], fit.scale, global_indices, global_weights
        )[0]
        for pathway_index, pathway in enumerate(source.pathways):
            naive_scores[held, pathway_index + 1] = _naive_score(
                cohort.primary_delta[held],
                fit,
                np.asarray(pathway.member_feature_indices, dtype=np.int64),
            )
        for patient in held:
            values = cohort.primary_delta[patient, inputs.union_indices] / scale
            valid = np.isfinite(values)
            full = _solve(design[valid], values[valid])
            nonconverged_by_role["full_patient"] += int(not full.converged)
            maximum_final_change_by_role["full_patient"] = max(
                maximum_final_change_by_role["full_patient"],
                full.final_max_change,
            )
            oof_coordinates[patient] = full.coordinates
            for gene_fold in range(GENE_FOLDS):
                validation = valid & (gene_folds == gene_fold)
                inference = valid & ~validation
                minimum_finite_held_gene_count = min(
                    minimum_finite_held_gene_count,
                    int(validation.sum()),
                )
                minimum_finite_inference_gene_count = min(
                    minimum_finite_inference_gene_count,
                    int(inference.sum()),
                )
                if int(validation.sum()) < 20:
                    raise ValueError("held gene fold has fewer than twenty values")
                global_fit = _solve(design[inference, :1], values[inference])
                joint_fit = _solve(design[inference], values[inference])
                nonconverged_by_role["global_held_gene"] += int(
                    not global_fit.converged
                )
                nonconverged_by_role["joint_held_gene"] += int(
                    not joint_fit.converged
                )
                maximum_final_change_by_role["global_held_gene"] = max(
                    maximum_final_change_by_role["global_held_gene"],
                    global_fit.final_max_change,
                )
                maximum_final_change_by_role["joint_held_gene"] = max(
                    maximum_final_change_by_role["joint_held_gene"],
                    joint_fit.final_max_change,
                )
                iteration_counts.extend((global_fit.iterations, joint_fit.iterations))
                global_prediction = design[validation, :1] @ global_fit.coordinates
                joint_prediction = design[validation] @ joint_fit.coordinates
                observed = values[validation]
                zero_mae = float(np.median(np.abs(observed)))
                global_mae = float(np.median(np.abs(observed - global_prediction)))
                joint_mae = float(np.median(np.abs(observed - joint_prediction)))
                zero_errors.append(zero_mae)
                global_errors.append(global_mae)
                joint_errors.append(joint_mae)
                global_rmse.append(
                    float(np.sqrt(np.mean((observed - global_prediction) ** 2)))
                )
                joint_rmse.append(
                    float(np.sqrt(np.mean((observed - joint_prediction) ** 2)))
                )
                per_patient_improvements[patient, gene_fold] = _relative_improvement(
                    global_mae, joint_mae
                )
                for pathway_index in range(len(source.pathways)):
                    keep = np.arange(design.shape[1]) != pathway_index + 1
                    omitted = _solve(design[inference][:, keep], values[inference])
                    nonconverged_by_role["leave_pathway_out"] += int(
                        not omitted.converged
                    )
                    maximum_final_change_by_role["leave_pathway_out"] = max(
                        maximum_final_change_by_role["leave_pathway_out"],
                        omitted.final_max_change,
                    )
                    omitted_prediction = design[validation][:, keep] @ omitted.coordinates
                    omitted_mae = float(np.median(np.abs(observed - omitted_prediction)))
                    removal_penalties[pathway_index].append(omitted_mae - joint_mae)

    zero = np.asarray(zero_errors, dtype=np.float64)
    global_values = np.asarray(global_errors, dtype=np.float64)
    joint_values = np.asarray(joint_errors, dtype=np.float64)
    improvement = (global_values - joint_values) / global_values
    rmse_improvement = (
        np.asarray(global_rmse) - np.asarray(joint_rmse)
    ) / np.asarray(global_rmse)
    patient_values = np.median(per_patient_improvements, axis=1)
    generator = np.random.default_rng(PATIENT_BOOTSTRAP_SEED)
    bootstrap_medians = np.median(
        patient_values[
            generator.integers(
                0,
                len(patient_values),
                size=(PATIENT_BOOTSTRAP_REPLICATES, len(patient_values)),
            )
        ],
        axis=1,
    )
    source_scales: list[dict[str, object]] = []
    names = ["global_recurrence"] + [item.reactome_id for item in source.pathways]
    for index, name in enumerate(names):
        values = oof_coordinates[:, index]
        median = float(np.median(values))
        mad_scale = 1.4826 * float(np.median(np.abs(values - median)))
        source_scales.append(
            {
                "component_id": name,
                "median": _q(median),
                "mad_scale": _q(mad_scale),
                "standard_deviation": _q(float(np.std(values, ddof=1))),
            }
        )

    correlations = _spearman(naive_scores)
    global_correlations = correlations[0, 1:]
    pathway_correlations = correlations[1:, 1:]
    upper = pathway_correlations[np.triu_indices(len(source.pathways), k=1)]
    removal = []
    for pathway, values in zip(source.pathways, removal_penalties, strict=True):
        array = np.asarray(values, dtype=np.float64)
        removal.append(
            {
                "reactome_id": pathway.reactome_id,
                "median_mae_penalty_when_removed": _q(float(np.median(array))),
                "mean_mae_penalty_when_removed": _q(float(np.mean(array))),
                "removal_worsened_fraction": _q(float(np.mean(array > 0.0))),
                "q05": _q(float(np.quantile(array, 0.05))),
                "q95": _q(float(np.quantile(array, 0.95))),
            }
        )
    cosine_matrix = np.stack(fold_cosines)
    evaluation = {
        "protocol": (
            "eight deterministic held-patient folds with all source statistics and "
            "loadings refit; five deterministic held-gene folds within each held patient"
        ),
        "validation_scope": "same-cohort reconstruction; not external validation",
        "patient_count": len(cohort.patient_groups),
        "evaluation_count": len(joint_errors),
        "union_feature_count": int(inputs.union_indices.size),
        "outer_fold_sizes": [len(fold) for fold in folds],
        "minimum_structural_gene_fold_count": int(
            min(
                np.sum(_gene_fold(cohort.genes, inputs.union_indices) == index)
                for index in range(GENE_FOLDS)
            )
        ),
        "minimum_finite_held_gene_count": minimum_finite_held_gene_count,
        "minimum_finite_inference_gene_count": minimum_finite_inference_gene_count,
        "zero_prediction_median_standardized_mae": _q(float(np.median(zero))),
        "global_only_median_standardized_mae": _q(float(np.median(global_values))),
        "joint_median_standardized_mae": _q(float(np.median(joint_values))),
        "median_relative_mae_improvement": _q(float(np.median(improvement))),
        "evaluation_improved_fraction": _q(float(np.mean(improvement > 0.0))),
        "median_relative_rmse_improvement": _q(float(np.median(rmse_improvement))),
        "patient_cluster_median_improvement": _q(float(np.median(patient_values))),
        "patient_cluster_improved_fraction": _q(float(np.mean(patient_values > 0.0))),
        "patient_cluster_bootstrap_replicates": PATIENT_BOOTSTRAP_REPLICATES,
        "patient_cluster_bootstrap_seed": PATIENT_BOOTSTRAP_SEED,
        "patient_cluster_median_improvement_90_interval": [
            _q(float(np.quantile(bootstrap_medians, 0.05))),
            _q(float(np.quantile(bootstrap_medians, 0.95))),
        ],
        "reference_design_condition_number": _q(float(np.linalg.cond(reference_design))),
        "outer_design_condition_minimum": _q(float(min(conditions))),
        "outer_design_condition_maximum": _q(float(max(conditions))),
        "outer_loading_cosine_minima": [_q(value) for value in cosine_matrix.min(axis=0)],
        "outer_loading_cosine_medians": [
            _q(value) for value in np.median(cosine_matrix, axis=0)
        ],
        "naive_pathway_global_spearman_minimum": _q(float(global_correlations.min())),
        "naive_pathway_global_spearman_maximum": _q(float(global_correlations.max())),
        "naive_pathway_pair_spearman_maximum": _q(float(upper.max())),
        "solver_iteration_maximum": max(iteration_counts),
        "solver_nonconverged_by_role": nonconverged_by_role,
        "solver_maximum_final_change_by_role": {
            key: _q(value) for key, value in maximum_final_change_by_role.items()
        },
        "leave_pathway_out": removal,
        "cross_fitted_coordinate_scales": source_scales,
        "interpretation": (
            "the joint dictionary has a modest collective reconstruction advantage; "
            "individual pathway attribution is not established by cohort-level removal"
        ),
    }
    return evaluation, oof_coordinates


def _bootstrap_seed(source_digest: str, recipe_digest: str, index: int) -> int:
    payload = f"{source_digest}:{recipe_digest}:bootstrap:{index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _bootstrap_ensemble(
    cohort: base.Cohort,
    inputs: DesignInputs,
    *,
    source_digest: str,
    recipe_digest: str,
    replicates: int,
) -> tuple[
    npt.NDArray[np.float32],
    npt.NDArray[np.float32],
    list[str],
]:
    scales = np.empty((replicates, inputs.union_indices.size), dtype=np.float32)
    effects = np.empty_like(scales)
    row_digests: list[str] = []
    for index in range(replicates):
        generator = np.random.default_rng(
            _bootstrap_seed(source_digest, recipe_digest, index)
        )
        selected = generator.integers(
            0,
            len(cohort.patient_groups),
            size=len(cohort.patient_groups),
        )
        fit = base._fit_axis(cohort.primary_delta[selected], cohort.genes)
        if not fit.converged:
            raise ValueError(f"source bootstrap fit {index} did not converge")
        scales[index] = fit.scale[inputs.union_indices]
        effects[index] = fit.effect[inputs.union_indices]
        row_digests.append(
            _raw_digest(scales[index].tobytes() + effects[index].tobytes())
        )
    return scales, effects, row_digests


def _assert_deidentified(
    artifact: dict[str, object], patient_groups: tuple[str, ...]
) -> None:
    payload = _canonical_bytes(artifact)
    forbidden_keys = (
        b'"patient_groups"',
        b'"patient_ids"',
        b'"patient_hashes"',
        b'"fold_membership"',
        b'"bootstrap_indices"',
        b'"patient_scores"',
        b'"patient_residuals"',
    )
    if any(token in payload for token in forbidden_keys):
        raise ValueError("fitted artifact contains a forbidden patient-level field")
    digest_tokens = set(
        __import__("re").findall(
            rb"(?<![0-9a-f])[0-9a-f]{32,128}(?![0-9a-f])", payload.lower()
        )
    )
    for patient in patient_groups:
        for identifier in (patient, f"{patient}_T1", f"{patient}_T2"):
            encoded = identifier.encode()
            if encoded in payload:
                raise ValueError("fitted artifact contains a patient identifier")
            hashes = {
                hashlib.md5(encoded, usedforsecurity=False).hexdigest().encode(),
                hashlib.sha1(encoded, usedforsecurity=False).hexdigest().encode(),
                hashlib.sha256(encoded).hexdigest().encode(),
                hashlib.sha512(encoded).hexdigest().encode(),
            }
            if not digest_tokens.isdisjoint(hashes):
                raise ValueError("fitted artifact contains a patient identifier hash")


def build_artifact(
    cohort: base.Cohort,
    *,
    bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
) -> dict[str, object]:
    """Fit and return the canonical de-identified model document."""

    if not 1 <= bootstrap_replicates <= DEFAULT_BOOTSTRAP_REPLICATES:
        raise ValueError("bootstrap replicate count must be between 1 and 256")
    source = reactome_transition_source_catalog()
    if cohort.genes != source.genes or len(cohort.patient_groups) != source.patient_count:
        raise ValueError("cohort axes do not match the admitted Reactome source catalog")
    inputs = _design_inputs(source)
    recipe = _recipe()
    recipe_digest = _digest(recipe)
    primary_fit = _view(base._fit_axis(cohort.primary_delta, cohort.genes))
    ordinary_fit = _view(base._fit_axis(cohort.ordinary_delta, cohort.genes))
    if not primary_fit.converged or not ordinary_fit.converged:
        raise ValueError("reference or source-processing fit did not converge")
    primary_design = _design(primary_fit, inputs)
    ordinary_design = _design(ordinary_fit, inputs)
    no_degree_design = _design(primary_fit, inputs, degree_normalization=False)
    evaluation, _ = _evaluation(cohort, source, inputs, primary_design)
    bootstrap_scale, bootstrap_effect, row_digests = _bootstrap_ensemble(
        cohort,
        inputs,
        source_digest=source.content_digest,
        recipe_digest=recipe_digest,
        replicates=bootstrap_replicates,
    )
    reference_scale = primary_fit.scale[inputs.union_indices]
    reference_effect = primary_fit.effect[inputs.union_indices]
    reference_support = primary_fit.support[inputs.union_indices]
    reference_eligible = primary_fit.eligible[inputs.union_indices]
    ordinary_effect = ordinary_fit.effect[inputs.union_indices]
    reference_tensors = {
        "scale": _tensor(reference_scale, "<f8"),
        "effect": _tensor(reference_effect, "<f8"),
        "support": _tensor(reference_support, "<i2"),
        "eligible": _tensor(reference_eligible, "|b1"),
    }
    ordinary_tensor = _tensor(ordinary_effect, "<f8")
    bootstrap_tensors = {
        "scale": _tensor(bootstrap_scale, "<f4"),
        "effect": _tensor(bootstrap_effect, "<f4"),
    }
    tensor_digest = _digest(reference_tensors)
    centering_scaling_digest = _digest(
        {
            key: reference_tensors[key]
            for key in ("scale", "support", "eligible")
        }
    )
    global_loading_digest = _raw_digest(
        np.ascontiguousarray(primary_design[:, 0], dtype="<f8").tobytes()
    )
    conditional_loading_digest = _raw_digest(
        np.ascontiguousarray(primary_design[:, 1:], dtype="<f8").tobytes()
    )
    fold_policy = {
        "outer_folds": OUTER_FOLDS,
        "held_gene_folds": GENE_FOLDS,
        "outer_fold_salt": OUTER_FOLD_SALT,
        "gene_fold_salt": GENE_FOLD_SALT,
        "patient_assignment": "SHA-256 ordering followed by balanced round-robin buckets",
        "gene_assignment": "first sixteen SHA-256 bits modulo held-gene fold count",
    }
    source_processing_digest = _digest(ordinary_tensor)
    bootstrap_digest = _digest(
        {"tensors": bootstrap_tensors, "row_digests": row_digests}
    )
    artifact: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "profile_id": PROFILE_ID,
        "artifact_role": ARTIFACT_ROLE,
        "source_catalog_binding": {
            "artifact_byte_digest": source.artifact_byte_digest,
            "content_digest": source.content_digest,
            "source_binding_digest": source.source_binding_digest,
            "selection_candidate_digest": source.selection_candidate_digest,
            "pathway_order_digest": source.pathway_order_digest,
            "pathway_membership_digest": source.pathway_membership_digest,
            "gene_order_digest": source.gene_order_digest,
            "patient_order_rule_digest": source.patient_order_rule_digest,
        },
        "training_recipe": recipe,
        "fold_policy": fold_policy,
        "counts": {
            "source_patient_pairs": len(cohort.patient_groups),
            "source_gene_features": len(cohort.genes),
            "union_features": int(inputs.union_indices.size),
            "pathways": len(source.pathways),
            "bootstrap_replicates": bootstrap_replicates,
        },
        "union_feature_indices": [int(value) for value in inputs.union_indices],
        "reference_fit": {
            "converged": primary_fit.converged,
            "iterations": primary_fit.iterations,
            "intensity_floor": _q(primary_fit.intensity_floor),
            "tensors": reference_tensors,
            "design_condition_number": _q(float(np.linalg.cond(primary_design))),
            "design_raw_sha256": _raw_digest(primary_design.astype("<f8").tobytes()),
        },
        "source_processing_ablation": {
            "measure": SOURCE_PROCESSING_ABLATION_MEASURE,
            "converged": ordinary_fit.converged,
            "iterations": ordinary_fit.iterations,
            "intensity_floor": _q(ordinary_fit.intensity_floor),
            "effect": ordinary_tensor,
            "loading_cosines": [
                _q(value)
                for value in _loading_cosines(primary_design, ordinary_design)
            ],
        },
        "degree_normalization_ablation": {
            "loading_cosines": [
                _q(value)
                for value in _loading_cosines(primary_design, no_degree_design)
            ]
        },
        "bootstrap": {
            "replicates": bootstrap_replicates,
            "resample_unit": "strict paired patient group",
            "patient_indices_or_hashes_bundled": False,
            "row_digests": row_digests,
            "tensors": bootstrap_tensors,
        },
        "evaluation": evaluation,
        "digests": {
            "training_recipe_digest": recipe_digest,
            "union_feature_digest": _digest(
                [int(value) for value in inputs.union_indices]
            ),
            "reference_tensor_digest": tensor_digest,
            "centering_scaling_digest": centering_scaling_digest,
            "reference_design_digest": _raw_digest(
                primary_design.astype("<f8").tobytes()
            ),
            "global_loading_digest": global_loading_digest,
            "conditional_loading_digest": conditional_loading_digest,
            "fold_policy_digest": _digest(fold_policy),
            "source_processing_ablation_digest": source_processing_digest,
            "bootstrap_ensemble_digest": bootstrap_digest,
            "evaluation_digest": _digest(evaluation),
        },
        "privacy": {
            "patient_measurements_bundled": False,
            "patient_identifiers_or_hashes_bundled": False,
            "patient_scores_or_residuals_bundled": False,
            "fold_membership_bundled": False,
            "bootstrap_resample_indices_bundled": False,
        },
        "provenance": {
            "study_id": "PDC000514",
            "article_doi": "10.1016/j.ccell.2023.12.015",
            "pdc_license": "CC-BY-4.0",
            "reactome_annotation_license": "CC0-1.0",
            "numpy_version": np.__version__,
        },
        "limitations": [
            "Research-use-only same-cohort protein-transition concordance model.",
            "The held-patient evaluation is internal reconstruction, not external validation.",
            "Reactome membership does not establish pathway activation, flux, or causality.",
            "The collective conditional reconstruction advantage is modest.",
            (
                "Cohort-level leave-pathway-out results do not establish individual "
                "pathway attribution."
            ),
            "PI3K/AKT has no unique member in the fixed panel and remains overlap-confounded.",
            "Missingness, preprocessing, sampling, and cohort transport remain limitations.",
            "Outputs are non-prescriptive and are not recurrence or treatment predictions.",
        ],
    }
    content_digest = _digest(artifact)
    artifact["artifact_digest"] = content_digest
    _assert_deidentified(artifact, cohort.patient_groups)
    return artifact


def write_artifact(document: dict[str, object], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_canonical_bytes(document))


def _default_output() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "glio_proteogen"
        / "research"
        / "longitudinal_gbm_reactome_transition"
        / "data"
        / "kncc_reactome_conditional_transition_model.v1.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdc-source-dir", type=Path, required=True)
    parser.add_argument("--hgnc-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=_default_output())
    parser.add_argument(
        "--bootstrap-replicates",
        type=int,
        default=DEFAULT_BOOTSTRAP_REPLICATES,
    )
    arguments = parser.parse_args()
    cohort = base.load_cohort(arguments.pdc_source_dir, arguments.hgnc_source)
    artifact = build_artifact(
        cohort,
        bootstrap_replicates=arguments.bootstrap_replicates,
    )
    write_artifact(artifact, arguments.output)
    payload = arguments.output.read_bytes()
    print(f"wrote {arguments.output}")
    print(f"bytes={len(payload)}")
    print(f"sha256={hashlib.sha256(payload).hexdigest()}")
    print(f"content_digest={artifact['artifact_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

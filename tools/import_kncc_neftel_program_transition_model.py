# ruff: noqa: C901, PLR0912, PLR0915, PLR2004, T201, TRY003
"""Fit the de-identified KNCC/Neftel conditional program-transition model.

This source-locked offline fitter consumes the verified PDC000514 paired protein
matrix and the already admitted Neftel Table S2 marker catalog. Patient
measurements, identifiers, hashes, scores, residuals, fold assignments, and
bootstrap resample indices are never serialized. Only aggregate evaluation and
fitted source-cohort coefficients are emitted.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple, cast

import numpy as np
import numpy.typing as npt

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.research.neftel_protein_programs.catalog import (
    EXPECTED_PROGRAM_ORDER,
    MarkerCatalog,
    marker_catalog,
)
from tools import import_kncc_longitudinal_gbm as base

MODEL_ID: Final = "kncc-neftel-program-transition-model/1.0.0"
PROFILE_ID: Final = "kncc-neftel-program-transition/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-neftel-program-transition-model/1.0.0"
ARTIFACT_ROLE: Final = (
    "de-identified fitted conditional bulk-protein program-transition concordance model"
)
PRIMARY_MEASURE: Final = "Unshared Log"
SOURCE_PROCESSING_ABLATION_MEASURE: Final = "Log"
OUTER_FOLDS: Final = 8
MARKER_FOLDS: Final = 5
OUTER_FOLD_SALT: Final = "kncc-neftel-program-outer-v1"
MARKER_FOLD_SALT: Final = "kncc-neftel-marker-fold-v1"
HUBER_K: Final = 1.345
RIDGE_LAMBDA: Final = 1.0
GLOBAL_RIDGE_MULTIPLIER: Final = 0.25
SOLVER_DAMPING: Final = 0.7
SOLVER_MAX_ITERATIONS: Final = 200
SOLVER_TOLERANCE: Final = 1.0e-9
DEFAULT_BOOTSTRAP_REPLICATES: Final = 128
PATIENT_CLUSTER_BOOTSTRAP_REPLICATES: Final = 20_000
PATIENT_CLUSTER_BOOTSTRAP_SEED: Final = 20_260_830
QUANTIZATION_DECIMALS: Final = 10

EXPECTED_SOURCE_PATIENT_PAIRS: Final = 104
EXPECTED_SOURCE_GENE_FEATURES: Final = 11_312
EXPECTED_UNION_FEATURES: Final = 256
EXPECTED_REFERENCE_ELIGIBLE_FEATURES: Final = 256
EXPECTED_MAPPED_COUNTS: Final = {
    "MES2": 42,
    "MES1": 49,
    "AC": 37,
    "OPC": 47,
    "NPC1": 43,
    "NPC2": 41,
    "G1/S": 26,
    "G2/M": 37,
}
EXPECTED_REFERENCE_ELIGIBLE_COUNTS: Final = {
    "MES2": 40,
    "MES1": 47,
    "AC": 36,
    "OPC": 46,
    "NPC1": 42,
    "NPC2": 38,
    "G1/S": 14,
    "G2/M": 25,
}

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class ProgramInputs:
    """One exact Neftel source program mapped onto the KNCC feature axis."""

    program_index: int
    program_id: str
    source_marker_count: int
    protein_eligible_marker_count: int
    mapped_symbols: tuple[str, ...]
    mapped_feature_indices: IntArray
    member_symbols: tuple[str, ...]
    member_feature_indices: IntArray
    member_local_indices: IntArray
    member_symbol_digest: str
    member_index_digest: str


@dataclass(frozen=True, slots=True)
class DesignInputs:
    """Fixed source topology used to derive the fitted loading dictionary."""

    union_indices: IntArray
    local_by_feature: dict[int, int]
    degree: FloatArray
    programs: tuple[ProgramInputs, ...]
    program_order_digest: str
    program_membership_digest: str


@dataclass(frozen=True, slots=True)
class FitView:
    """Minimal view of a source fit used by this importer."""

    scale: FloatArray
    support: IntArray
    eligible: BoolArray
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
    if not math.isfinite(float(value)):
        raise ValueError("cannot quantize a non-finite fitted value")
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


def _pdc_source_binding() -> dict[str, object]:
    return {
        "pdc_study_id": base.PDC_STUDY_ID,
        "pdc_study_version_uuid": base.PDC_STUDY_VERSION_UUID,
        "versioned_source_manifest": {
            "filename": base.PDC_SOURCE_MANIFEST_FILENAME,
            "bytes": base.PDC_SOURCE_MANIFEST_BYTES,
            "sha256": f"sha256:{base.PDC_SOURCE_MANIFEST_SHA256}",
            "schema_version": base.PDC_SOURCE_MANIFEST_SCHEMA,
            "graphql_api_version": base.PDC_GRAPHQL_API_VERSION,
        },
        "files": [
            {
                "filename": item.filename,
                "uuid": item.uuid,
                "bytes": item.bytes,
                "md5": item.md5,
                "sha256": f"sha256:{item.sha256}",
            }
            for item in base.SOURCE_FILES
        ],
        "hgnc_authority": {
            "filename": base.HGNC_SOURCE_FILENAME,
            "bytes": base.HGNC_SOURCE_BYTES,
            "sha256": f"sha256:{base.HGNC_SOURCE_SHA256}",
        },
        "primary_measure": PRIMARY_MEASURE,
        "source_processing_ablation_measure": SOURCE_PROCESSING_ABLATION_MEASURE,
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
        "held_marker_folds": MARKER_FOLDS,
        "outer_fold_salt": OUTER_FOLD_SALT,
        "marker_fold_salt": MARKER_FOLD_SALT,
        "program_order": list(EXPECTED_PROGRAM_ORDER),
        "shared_marker_weight": "inverse square root of source-program membership degree",
        "conditional_adjustment": "orthogonal projection against fitted global loading",
        "conditional_loading_source": (
            "training-only robust standardized source effects within fixed Neftel masks"
        ),
        "equal_membership_baseline": (
            "unit marker mass within fixed Neftel masks with the same overlap correction "
            "and global residualization"
        ),
        "loading_l2_norm": 1.0,
        "design_row_scale": "square root of mapped union feature count",
        "solver": "deterministic damped Huber IRLS coordinate descent",
        "solver_huber_k": HUBER_K,
        "solver_ridge_lambda": RIDGE_LAMBDA,
        "solver_global_ridge_multiplier": GLOBAL_RIDGE_MULTIPLIER,
        "solver_damping": SOLVER_DAMPING,
        "solver_max_iterations": SOLVER_MAX_ITERATIONS,
        "solver_tolerance": SOLVER_TOLERANCE,
        "bootstrap_generator": "numpy.random.Generator(PCG64)",
        "bootstrap_seed_policy": (
            "first 64 SHA-256 bits of the biological source-projection namespace, "
            "recipe digest, and zero-based replicate index"
        ),
        "bootstrap_resample_unit": "strict paired patient group",
        "coefficient_storage": "little-endian float32 bootstrap tensors",
        "reference_storage": "little-endian float64 tensors",
        "quantization_decimals": QUANTIZATION_DECIMALS,
        "claim_ceiling": (
            "paired PDC000514 source-cohort bulk-protein transition concordance "
            "conditional on exact Neftel marker sets"
        ),
    }


def _design_inputs(
    genes: tuple[str, ...],
    catalog: MarkerCatalog | None = None,
    *,
    eligible_mask: BoolArray | None = None,
    enforce_source_oracles: bool = False,
) -> DesignInputs:
    source = catalog or marker_catalog()
    if len(genes) != len(set(genes)):
        raise ValueError("KNCC feature axis contains duplicate gene symbols")
    if tuple(source.programs) != EXPECTED_PROGRAM_ORDER:
        raise ValueError("Neftel source program order changed")
    if eligible_mask is not None and (
        eligible_mask.shape != (len(genes),) or eligible_mask.dtype != np.bool_
    ):
        raise ValueError("reference eligibility mask does not match the KNCC feature axis")
    feature_by_symbol = {symbol: index for index, symbol in enumerate(genes)}
    provisional: list[
        tuple[str, int, int, tuple[str, ...], IntArray, tuple[str, ...], IntArray]
    ] = []
    union_members: set[int] = set()
    for program_id in EXPECTED_PROGRAM_ORDER:
        markers = source.programs[program_id]
        protein_markers = tuple(marker for marker in markers if marker.protein_eligible)
        mapped_symbols = tuple(
            marker.normalized_symbol
            for marker in protein_markers
            if marker.normalized_symbol in feature_by_symbol
        )
        if len(mapped_symbols) != len(set(mapped_symbols)):
            raise ValueError(f"Neftel program {program_id} maps one protein more than once")
        mapped_indices = np.asarray(
            [feature_by_symbol[symbol] for symbol in mapped_symbols], dtype=np.int64
        )
        if mapped_indices.size < 3:
            raise ValueError(f"Neftel program {program_id} has fewer than three mapped proteins")
        if enforce_source_oracles and mapped_indices.size != EXPECTED_MAPPED_COUNTS[program_id]:
            raise ValueError(f"Neftel program {program_id} mapped-feature oracle changed")
        if eligible_mask is None:
            member_symbols = mapped_symbols
            member_indices = mapped_indices
        else:
            selected = eligible_mask[mapped_indices]
            member_symbols = tuple(
                symbol
                for symbol, include in zip(mapped_symbols, selected, strict=True)
                if bool(include)
            )
            member_indices = mapped_indices[selected]
        if member_indices.size < 3:
            raise ValueError(f"Neftel program {program_id} has fewer than three fitted proteins")
        if (
            enforce_source_oracles
            and member_indices.size != EXPECTED_REFERENCE_ELIGIBLE_COUNTS[program_id]
        ):
            raise ValueError(f"Neftel program {program_id} fitted-feature oracle changed")
        provisional.append(
            (
                program_id,
                len(markers),
                len(protein_markers),
                mapped_symbols,
                mapped_indices,
                member_symbols,
                member_indices,
            )
        )
        union_members.update(int(value) for value in member_indices)
    union = np.asarray(sorted(union_members), dtype=np.int64)
    if enforce_source_oracles and union.size != EXPECTED_UNION_FEATURES:
        raise ValueError("KNCC/Neftel mapped-union feature oracle changed")
    local = {int(feature): index for index, feature in enumerate(union)}
    degree = np.zeros(union.size, dtype=np.float64)
    programs: list[ProgramInputs] = []
    membership_projection: list[dict[str, object]] = []
    for program_index, (
        program_id,
        source_count,
        protein_count,
        mapped_symbols,
        mapped_indices,
        symbols,
        indices,
    ) in enumerate(provisional):
        local_indices = np.asarray([local[int(value)] for value in indices], dtype=np.int64)
        degree[local_indices] += 1.0
        symbol_digest = _digest(list(symbols))
        index_digest = _digest([int(value) for value in indices])
        programs.append(
            ProgramInputs(
                program_index=program_index,
                program_id=program_id,
                source_marker_count=source_count,
                protein_eligible_marker_count=protein_count,
                mapped_symbols=mapped_symbols,
                mapped_feature_indices=mapped_indices,
                member_symbols=symbols,
                member_feature_indices=indices,
                member_local_indices=local_indices,
                member_symbol_digest=symbol_digest,
                member_index_digest=index_digest,
            )
        )
        membership_projection.append(
            {
                "program_id": program_id,
                "mapped_symbols": list(mapped_symbols),
                "mapped_feature_indices": [int(value) for value in mapped_indices],
                "member_symbols": list(symbols),
                "member_feature_indices": [int(value) for value in indices],
            }
        )
    if union.size == 0 or np.any(degree < 1.0):
        raise ValueError("KNCC/Neftel fitted union is empty or has invalid membership degree")
    return DesignInputs(
        union_indices=union,
        local_by_feature=local,
        degree=degree,
        programs=tuple(programs),
        program_order_digest=_digest(list(EXPECTED_PROGRAM_ORDER)),
        program_membership_digest=_digest(membership_projection),
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


def _global_loading(fit: FitView, inputs: DesignInputs) -> FloatArray:
    effect = np.where(
        fit.eligible[inputs.union_indices],
        fit.effect[inputs.union_indices],
        0.0,
    )
    norm = float(np.linalg.norm(effect))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError("global recurrence loading has zero or non-finite norm")
    return effect / norm


def _design(
    fit: FitView,
    inputs: DesignInputs,
    *,
    degree_normalization: bool = True,
) -> FloatArray:
    effect = fit.effect[inputs.union_indices]
    global_loading = _global_loading(fit, inputs)
    columns: list[FloatArray] = [global_loading]
    for program in inputs.programs:
        raw = np.zeros(inputs.union_indices.size, dtype=np.float64)
        feature_indices = inputs.union_indices[program.member_local_indices]
        active = fit.eligible[feature_indices]
        positions = program.member_local_indices[active]
        divisor: FloatArray | float
        divisor = np.sqrt(inputs.degree[positions]) if degree_normalization else 1.0
        raw[positions] = effect[positions] / divisor
        raw -= global_loading * float(np.dot(global_loading, raw))
        norm = float(np.linalg.norm(raw))
        if not math.isfinite(norm) or norm <= 0.0:
            raise ValueError(
                f"conditional Neftel loading {program.program_id} has zero or non-finite norm"
            )
        columns.append(raw / norm)
    design = np.column_stack(columns) * math.sqrt(inputs.union_indices.size)
    if not np.all(np.isfinite(design)):
        raise ValueError("KNCC/Neftel design contains a non-finite loading")
    return design


def _equal_membership_design(fit: FitView, inputs: DesignInputs) -> FloatArray:
    global_loading = _global_loading(fit, inputs)
    columns: list[FloatArray] = [global_loading]
    for program in inputs.programs:
        raw = np.zeros(inputs.union_indices.size, dtype=np.float64)
        feature_indices = inputs.union_indices[program.member_local_indices]
        active = fit.eligible[feature_indices]
        positions = program.member_local_indices[active]
        raw[positions] = 1.0 / np.sqrt(inputs.degree[positions])
        raw -= global_loading * float(np.dot(global_loading, raw))
        norm = float(np.linalg.norm(raw))
        if not math.isfinite(norm) or norm <= 0.0:
            raise ValueError(
                f"equal-membership baseline {program.program_id} has zero or non-finite norm"
            )
        columns.append(raw / norm)
    return np.column_stack(columns) * math.sqrt(inputs.union_indices.size)


def _solve(design: FloatArray, values: FloatArray) -> SolveOutcome:
    if design.ndim != 2 or values.ndim != 1 or design.shape[0] != values.size:
        raise ValueError("solver design/value shape mismatch")
    if (
        values.size < design.shape[1]
        or not np.all(np.isfinite(design))
        or not np.all(np.isfinite(values))
    ):
        raise ValueError("solver requires finite overdetermined evidence")
    coordinates = np.zeros(design.shape[1], dtype=np.float64)
    penalty = np.eye(design.shape[1], dtype=np.float64)
    penalty[0, 0] = GLOBAL_RIDGE_MULTIPLIER
    final_change = math.inf
    for iteration in range(1, SOLVER_MAX_ITERATIONS + 1):
        residual = values - design @ coordinates
        weights = np.minimum(1.0, HUBER_K / np.maximum(np.abs(residual), 1.0e-12))
        system = design.T @ (weights[:, None] * design) + RIDGE_LAMBDA * penalty
        target = design.T @ (weights * values)
        updated = np.linalg.solve(system, target)
        final_change = float(np.max(np.abs(updated - coordinates)))
        if not math.isfinite(final_change) or not np.all(np.isfinite(updated)):
            raise ValueError("IRLS coordinate solver produced a non-finite update")
        if final_change < SOLVER_TOLERANCE:
            return SolveOutcome(
                coordinates=updated,
                iterations=iteration,
                converged=True,
                final_max_change=final_change,
            )
        coordinates = SOLVER_DAMPING * updated + (1.0 - SOLVER_DAMPING) * coordinates
    return SolveOutcome(
        coordinates=coordinates,
        iterations=SOLVER_MAX_ITERATIONS,
        converged=False,
        final_max_change=final_change,
    )


def _marker_fold(genes: tuple[str, ...], feature_indices: IntArray) -> IntArray:
    return np.asarray(
        [
            int.from_bytes(
                hashlib.sha256(f"{MARKER_FOLD_SALT}:{genes[int(index)]}".encode()).digest()[:2],
                "big",
            )
            % MARKER_FOLDS
            for index in feature_indices
        ],
        dtype=np.int64,
    )


def _relative_improvement(reference: float, candidate: float) -> float:
    return (reference - candidate) / reference if reference > 0.0 else 0.0


def _loading_cosines(left: FloatArray, right: FloatArray) -> FloatArray:
    numerator = np.sum(left * right, axis=0)
    denominator = np.linalg.norm(left, axis=0) * np.linalg.norm(right, axis=0)
    if np.any(denominator <= 0.0):
        raise ValueError("loading cosine has a zero-norm column")
    return numerator / denominator


def _cluster_interval(values: FloatArray, draws: IntArray) -> list[float]:
    medians = np.median(values[draws], axis=1)
    return [
        _q(float(np.quantile(medians, 0.05))),
        _q(float(np.quantile(medians, 0.95))),
    ]


def _evaluation(
    cohort: base.Cohort,
    inputs: DesignInputs,
    reference_design: FloatArray,
    reference_equal_design: FloatArray,
) -> tuple[dict[str, object], FloatArray]:
    folds = base._folds(cohort.patient_groups, OUTER_FOLDS, OUTER_FOLD_SALT)
    all_indices = np.arange(len(cohort.patient_groups), dtype=np.int64)
    marker_folds = _marker_fold(cohort.genes, inputs.union_indices)
    zero_errors: list[float] = []
    global_errors: list[float] = []
    equal_errors: list[float] = []
    joint_errors: list[float] = []
    global_rmse: list[float] = []
    equal_rmse: list[float] = []
    joint_rmse: list[float] = []
    per_patient_global_gain = np.empty((len(cohort.patient_groups), MARKER_FOLDS), dtype=np.float64)
    per_patient_equal_gain = np.empty_like(per_patient_global_gain)
    removal_penalties: list[list[float]] = [[] for _ in inputs.programs]
    conditions: list[float] = []
    equal_conditions: list[float] = []
    fold_cosines: list[FloatArray] = []
    oof_coordinates = np.empty(
        (len(cohort.patient_groups), 1 + len(inputs.programs)), dtype=np.float64
    )
    iteration_counts: list[int] = []
    nonconverged_by_role = {
        "full_patient": 0,
        "global_held_marker": 0,
        "equal_membership_held_marker": 0,
        "joint_held_marker": 0,
        "leave_program_out": 0,
    }
    maximum_final_change_by_role = dict.fromkeys(nonconverged_by_role, 0.0)
    minimum_finite_held_marker_count = inputs.union_indices.size
    minimum_finite_inference_marker_count = inputs.union_indices.size
    for held in folds:
        train = np.setdiff1d(all_indices, held, assume_unique=True)
        fit = _view(base._fit_axis(cohort.primary_delta[train], cohort.genes))
        if not fit.converged:
            raise ValueError("outer training-fold robust source fit did not converge")
        design = _design(fit, inputs)
        equal_design = _equal_membership_design(fit, inputs)
        conditions.append(float(np.linalg.cond(design)))
        equal_conditions.append(float(np.linalg.cond(equal_design)))
        fold_cosines.append(_loading_cosines(design, reference_design))
        scale = fit.scale[inputs.union_indices]
        for patient in held:
            values = cohort.primary_delta[patient, inputs.union_indices] / scale
            valid = np.isfinite(values)
            full = _solve(design[valid], values[valid])
            nonconverged_by_role["full_patient"] += int(not full.converged)
            maximum_final_change_by_role["full_patient"] = max(
                maximum_final_change_by_role["full_patient"], full.final_max_change
            )
            oof_coordinates[patient] = full.coordinates
            for marker_fold in range(MARKER_FOLDS):
                validation = valid & (marker_folds == marker_fold)
                inference = valid & ~validation
                held_count = int(validation.sum())
                inference_count = int(inference.sum())
                minimum_finite_held_marker_count = min(minimum_finite_held_marker_count, held_count)
                minimum_finite_inference_marker_count = min(
                    minimum_finite_inference_marker_count, inference_count
                )
                if held_count < 10 or inference_count < design.shape[1]:
                    raise ValueError("held-marker split has insufficient finite evidence")
                global_fit = _solve(design[inference, :1], values[inference])
                equal_fit = _solve(equal_design[inference], values[inference])
                joint_fit = _solve(design[inference], values[inference])
                for role, solved in (
                    ("global_held_marker", global_fit),
                    ("equal_membership_held_marker", equal_fit),
                    ("joint_held_marker", joint_fit),
                ):
                    nonconverged_by_role[role] += int(not solved.converged)
                    maximum_final_change_by_role[role] = max(
                        maximum_final_change_by_role[role], solved.final_max_change
                    )
                    iteration_counts.append(solved.iterations)
                global_prediction = design[validation, :1] @ global_fit.coordinates
                equal_prediction = equal_design[validation] @ equal_fit.coordinates
                joint_prediction = design[validation] @ joint_fit.coordinates
                observed = values[validation]
                zero_mae = float(np.median(np.abs(observed)))
                global_mae = float(np.median(np.abs(observed - global_prediction)))
                equal_mae = float(np.median(np.abs(observed - equal_prediction)))
                joint_mae = float(np.median(np.abs(observed - joint_prediction)))
                zero_errors.append(zero_mae)
                global_errors.append(global_mae)
                equal_errors.append(equal_mae)
                joint_errors.append(joint_mae)
                global_rmse.append(float(np.sqrt(np.mean((observed - global_prediction) ** 2))))
                equal_rmse.append(float(np.sqrt(np.mean((observed - equal_prediction) ** 2))))
                joint_rmse.append(float(np.sqrt(np.mean((observed - joint_prediction) ** 2))))
                per_patient_global_gain[patient, marker_fold] = _relative_improvement(
                    global_mae, joint_mae
                )
                per_patient_equal_gain[patient, marker_fold] = _relative_improvement(
                    equal_mae, joint_mae
                )
                for program_index in range(len(inputs.programs)):
                    keep = np.arange(design.shape[1]) != program_index + 1
                    omitted = _solve(design[inference][:, keep], values[inference])
                    nonconverged_by_role["leave_program_out"] += int(not omitted.converged)
                    maximum_final_change_by_role["leave_program_out"] = max(
                        maximum_final_change_by_role["leave_program_out"],
                        omitted.final_max_change,
                    )
                    omitted_prediction = design[validation][:, keep] @ omitted.coordinates
                    omitted_mae = float(np.median(np.abs(observed - omitted_prediction)))
                    removal_penalties[program_index].append(omitted_mae - joint_mae)

    zero = np.asarray(zero_errors, dtype=np.float64)
    global_values = np.asarray(global_errors, dtype=np.float64)
    equal_values = np.asarray(equal_errors, dtype=np.float64)
    joint_values = np.asarray(joint_errors, dtype=np.float64)
    global_gain = (global_values - joint_values) / global_values
    equal_gain = (equal_values - joint_values) / equal_values
    global_rmse_gain = (np.asarray(global_rmse) - np.asarray(joint_rmse)) / np.asarray(global_rmse)
    equal_rmse_gain = (np.asarray(equal_rmse) - np.asarray(joint_rmse)) / np.asarray(equal_rmse)
    patient_global_gain = np.median(per_patient_global_gain, axis=1)
    patient_equal_gain = np.median(per_patient_equal_gain, axis=1)
    generator = np.random.default_rng(PATIENT_CLUSTER_BOOTSTRAP_SEED)
    draws = generator.integers(
        0,
        len(cohort.patient_groups),
        size=(PATIENT_CLUSTER_BOOTSTRAP_REPLICATES, len(cohort.patient_groups)),
    )
    source_scales: list[dict[str, object]] = []
    component_ids = (
        "global_recurrence",
        *(program.program_id for program in inputs.programs),
    )
    for index, component_id in enumerate(component_ids):
        values = oof_coordinates[:, index]
        median = float(np.median(values))
        mad_scale = 1.4826 * float(np.median(np.abs(values - median)))
        source_scales.append(
            {
                "component_id": component_id,
                "median": _q(median),
                "mad_scale": _q(mad_scale),
                "standard_deviation": _q(float(np.std(values, ddof=1))),
            }
        )
    removal: list[dict[str, object]] = []
    for program, values in zip(inputs.programs, removal_penalties, strict=True):
        array = np.asarray(values, dtype=np.float64)
        removal.append(
            {
                "program_id": program.program_id,
                "median_mae_penalty_when_removed": _q(float(np.median(array))),
                "mean_mae_penalty_when_removed": _q(float(np.mean(array))),
                "removal_worsened_fraction": _q(float(np.mean(array > 0.0))),
                "q05": _q(float(np.quantile(array, 0.05))),
                "q95": _q(float(np.quantile(array, 0.95))),
            }
        )
    cosine_matrix = np.stack(fold_cosines)
    global_gain_interval = _cluster_interval(patient_global_gain, draws)
    equal_gain_interval = _cluster_interval(patient_equal_gain, draws)
    individually_supported_programs = [
        str(item["program_id"]) for item in removal if cast("float", item["q05"]) > 0.0
    ]
    evaluation = {
        "protocol": (
            "eight deterministic held-patient folds with all source statistics and "
            "loadings refit; five deterministic held-marker folds within each held patient"
        ),
        "validation_scope": "same-cohort held-marker reconstruction; not external validation",
        "patient_count": len(cohort.patient_groups),
        "evaluation_count": len(joint_errors),
        "union_feature_count": int(inputs.union_indices.size),
        "outer_fold_sizes": [len(fold) for fold in folds],
        "minimum_structural_marker_fold_count": int(
            min(np.sum(marker_folds == index) for index in range(MARKER_FOLDS))
        ),
        "minimum_finite_held_marker_count": minimum_finite_held_marker_count,
        "minimum_finite_inference_marker_count": minimum_finite_inference_marker_count,
        "zero_prediction_median_standardized_mae": _q(float(np.median(zero))),
        "global_only_median_standardized_mae": _q(float(np.median(global_values))),
        "equal_membership_median_standardized_mae": _q(float(np.median(equal_values))),
        "joint_median_standardized_mae": _q(float(np.median(joint_values))),
        "joint_vs_global_median_relative_mae_gain": _q(float(np.median(global_gain))),
        "joint_vs_equal_median_relative_mae_gain": _q(float(np.median(equal_gain))),
        "joint_vs_global_evaluation_improved_fraction": _q(float(np.mean(global_gain > 0.0))),
        "joint_vs_equal_evaluation_improved_fraction": _q(float(np.mean(equal_gain > 0.0))),
        "joint_vs_global_median_relative_rmse_gain": _q(float(np.median(global_rmse_gain))),
        "joint_vs_equal_median_relative_rmse_gain": _q(float(np.median(equal_rmse_gain))),
        "patient_cluster_joint_vs_global_median_gain": _q(float(np.median(patient_global_gain))),
        "patient_cluster_joint_vs_equal_median_gain": _q(float(np.median(patient_equal_gain))),
        "patient_cluster_joint_vs_global_improved_fraction": _q(
            float(np.mean(patient_global_gain > 0.0))
        ),
        "patient_cluster_joint_vs_equal_improved_fraction": _q(
            float(np.mean(patient_equal_gain > 0.0))
        ),
        "patient_cluster_bootstrap_replicates": PATIENT_CLUSTER_BOOTSTRAP_REPLICATES,
        "patient_cluster_bootstrap_seed": PATIENT_CLUSTER_BOOTSTRAP_SEED,
        "patient_cluster_joint_vs_global_median_gain_90_interval": global_gain_interval,
        "patient_cluster_joint_vs_equal_median_gain_90_interval": equal_gain_interval,
        "joint_vs_global_patient_cluster_interval_supports_positive_gain": (
            global_gain_interval[0] > 0.0
        ),
        "joint_vs_equal_patient_cluster_interval_supports_positive_gain": (
            equal_gain_interval[0] > 0.0
        ),
        "individually_supported_program_ids": individually_supported_programs,
        "release_gate": (
            "limited_fitted_dictionary_not_preferred_to_equal_membership"
            if equal_gain_interval[0] <= 0.0
            else "fitted_dictionary_preferred_to_equal_membership"
        ),
        "reference_design_condition_number": _q(float(np.linalg.cond(reference_design))),
        "equal_membership_reference_design_condition_number": _q(
            float(np.linalg.cond(reference_equal_design))
        ),
        "outer_design_condition_minimum": _q(float(min(conditions))),
        "outer_design_condition_maximum": _q(float(max(conditions))),
        "outer_equal_membership_condition_minimum": _q(float(min(equal_conditions))),
        "outer_equal_membership_condition_maximum": _q(float(max(equal_conditions))),
        "outer_loading_cosine_minima": [_q(value) for value in cosine_matrix.min(axis=0)],
        "outer_loading_cosine_medians": [_q(value) for value in np.median(cosine_matrix, axis=0)],
        "solver_iteration_maximum": max(iteration_counts),
        "solver_nonconverged_by_role": nonconverged_by_role,
        "solver_maximum_final_change_by_role": {
            key: _q(value) for key, value in maximum_final_change_by_role.items()
        },
        "leave_program_out": removal,
        "cross_fitted_coordinate_scales": source_scales,
        "interpretation": (
            "aggregate metrics compare a fitted conditional program dictionary with zero, "
            "global-only, and equal-membership baselines; individual program evidence is "
            "limited to its held-marker removal interval"
        ),
    }
    return evaluation, oof_coordinates


def _bootstrap_seed_namespace(
    inputs: DesignInputs,
    catalog: MarkerCatalog,
    recipe_digest: str,
) -> str:
    return _digest(
        {
            "pdc_source_binding_digest": _digest(_pdc_source_binding()),
            "neftel_source_program_digest": catalog.source_program_digest,
            "program_order_digest": inputs.program_order_digest,
            "program_membership_digest": inputs.program_membership_digest,
            "recipe_digest": recipe_digest,
        }
    )


def _bootstrap_seed(namespace_digest: str, index: int) -> int:
    payload = f"{namespace_digest}:bootstrap:{index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _bootstrap_ensemble(
    cohort: base.Cohort,
    inputs: DesignInputs,
    *,
    seed_namespace_digest: str,
    replicates: int,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.float32], list[str]]:
    scales = np.empty((replicates, inputs.union_indices.size), dtype=np.float32)
    effects = np.empty_like(scales)
    row_digests: list[str] = []
    for index in range(replicates):
        generator = np.random.default_rng(_bootstrap_seed(seed_namespace_digest, index))
        selected = generator.integers(
            0, len(cohort.patient_groups), size=len(cohort.patient_groups)
        )
        fit = _view(base._fit_axis(cohort.primary_delta[selected], cohort.genes))
        if not fit.converged:
            raise ValueError(f"source bootstrap fit {index} did not converge")
        _design(fit, inputs)
        scales[index] = fit.scale[inputs.union_indices]
        effects[index] = fit.effect[inputs.union_indices]
        row_digests.append(_raw_digest(scales[index].tobytes() + effects[index].tobytes()))
    return scales, effects, row_digests


def _assert_deidentified(artifact: dict[str, object], patient_groups: tuple[str, ...]) -> None:
    payload = _canonical_bytes(artifact)
    forbidden_keys = (
        b'"patient_groups"',
        b'"patient_ids"',
        b'"patient_hashes"',
        b'"fold_membership"',
        b'"fold_assignments"',
        b'"bootstrap_indices"',
        b'"resample_indices"',
        b'"patient_scores"',
        b'"patient_residuals"',
        b'"predictions"',
    )
    if any(token in payload for token in forbidden_keys):
        raise ValueError("fitted artifact contains a forbidden patient-level field")
    digest_tokens = set(re.findall(rb"(?<![0-9a-f])[0-9a-f]{32,128}(?![0-9a-f])", payload.lower()))
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


def _program_documents(inputs: DesignInputs, fit: FitView) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for program in inputs.programs:
        eligible_count = int(fit.eligible[program.member_feature_indices].sum())
        expected = EXPECTED_REFERENCE_ELIGIBLE_COUNTS[program.program_id]
        if eligible_count != expected or program.member_feature_indices.size != expected:
            raise ValueError(f"Neftel program {program.program_id} eligible-feature oracle changed")
        documents.append(
            {
                "program_index": program.program_index,
                "program_id": program.program_id,
                "source_marker_count": program.source_marker_count,
                "protein_eligible_marker_count": program.protein_eligible_marker_count,
                "mapped_feature_count": int(program.mapped_feature_indices.size),
                "reference_eligible_feature_count": eligible_count,
                "mapped_feature_indices": [int(value) for value in program.mapped_feature_indices],
                "member_feature_indices": [int(value) for value in program.member_feature_indices],
                "member_local_indices": [int(value) for value in program.member_local_indices],
                "member_symbol_digest": program.member_symbol_digest,
                "member_index_digest": program.member_index_digest,
            }
        )
    return documents


def build_artifact(
    cohort: base.Cohort,
    *,
    bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
) -> dict[str, object]:
    """Fit and return the canonical de-identified model document."""

    if not 1 <= bootstrap_replicates <= DEFAULT_BOOTSTRAP_REPLICATES:
        raise ValueError("bootstrap replicate count must be between 1 and 128")
    if (
        len(cohort.patient_groups) != EXPECTED_SOURCE_PATIENT_PAIRS
        or len(cohort.genes) != EXPECTED_SOURCE_GENE_FEATURES
        or cohort.primary_delta.shape
        != (EXPECTED_SOURCE_PATIENT_PAIRS, EXPECTED_SOURCE_GENE_FEATURES)
        or cohort.ordinary_delta.shape != cohort.primary_delta.shape
    ):
        raise ValueError("cohort axes do not match the exact PDC000514 source cohort")
    source = marker_catalog()
    recipe = _recipe()
    recipe_digest = _digest(recipe)
    pdc_binding = _pdc_source_binding()
    pdc_binding_digest = _digest(pdc_binding)
    primary_fit = _view(base._fit_axis(cohort.primary_delta, cohort.genes))
    ordinary_fit = _view(base._fit_axis(cohort.ordinary_delta, cohort.genes))
    if not primary_fit.converged or not ordinary_fit.converged:
        raise ValueError("reference or source-processing fit did not converge")
    inputs = _design_inputs(
        cohort.genes,
        source,
        eligible_mask=primary_fit.eligible,
        enforce_source_oracles=True,
    )
    if inputs.union_indices.size != EXPECTED_REFERENCE_ELIGIBLE_FEATURES:
        raise ValueError("KNCC/Neftel eligible-union feature oracle changed")
    primary_design = _design(primary_fit, inputs)
    equal_design = _equal_membership_design(primary_fit, inputs)
    ordinary_design = _design(ordinary_fit, inputs)
    no_degree_design = _design(primary_fit, inputs, degree_normalization=False)
    evaluation, _ = _evaluation(cohort, inputs, primary_design, equal_design)
    seed_namespace_digest = _bootstrap_seed_namespace(inputs, source, recipe_digest)
    bootstrap_scale, bootstrap_effect, row_digests = _bootstrap_ensemble(
        cohort,
        inputs,
        seed_namespace_digest=seed_namespace_digest,
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
    degree_tensor = _tensor(inputs.degree.astype(np.int16), "<i2")
    bootstrap_tensors = {
        "scale": _tensor(bootstrap_scale, "<f4"),
        "effect": _tensor(bootstrap_effect, "<f4"),
    }
    program_documents = _program_documents(inputs, primary_fit)
    fold_policy = {
        "outer_folds": OUTER_FOLDS,
        "held_marker_folds": MARKER_FOLDS,
        "outer_fold_salt": OUTER_FOLD_SALT,
        "marker_fold_salt": MARKER_FOLD_SALT,
        "patient_assignment": "SHA-256 ordering followed by balanced round-robin buckets",
        "marker_assignment": "first sixteen SHA-256 bits modulo held-marker fold count",
        "reference_availability_union": (
            "frozen 256-feature eligibility projection from the independently locked "
            "parent KNCC source artifact"
        ),
        "outer_training_refit_scope": (
            "locations, scales, finite support, fold-local eligibility, source effects, "
            "global loading, and all conditional loadings"
        ),
    }
    source_catalog_binding = {
        "pdc_source_binding": pdc_binding,
        "pdc_source_binding_digest": pdc_binding_digest,
        "neftel_catalog_artifact_digest": source.artifact_digest,
        "neftel_catalog_content_digest": source.content_digest,
        "neftel_source_program_digest": source.source_program_digest,
        "neftel_source_sha256": source.source_sha256,
        "neftel_hgnc_sha256": source.hgnc_sha256,
        "neftel_protein_background_digest": source.protein_background_digest,
        "program_order_digest": inputs.program_order_digest,
        "program_membership_digest": inputs.program_membership_digest,
    }
    bootstrap_digest = _digest({"tensors": bootstrap_tensors, "row_digests": row_digests})
    artifact: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "profile_id": PROFILE_ID,
        "artifact_role": ARTIFACT_ROLE,
        "source_catalog_binding": source_catalog_binding,
        "training_recipe": recipe,
        "fold_policy": fold_policy,
        "counts": {
            "source_patient_pairs": len(cohort.patient_groups),
            "source_gene_features": len(cohort.genes),
            "union_features": int(inputs.union_indices.size),
            "reference_eligible_union_features": int(reference_eligible.sum()),
            "programs": len(inputs.programs),
            "bootstrap_replicates": bootstrap_replicates,
        },
        "union_feature_indices": [int(value) for value in inputs.union_indices],
        "programs": program_documents,
        "membership_degree": degree_tensor,
        "reference_fit": {
            "converged": primary_fit.converged,
            "iterations": primary_fit.iterations,
            "intensity_floor": _q(primary_fit.intensity_floor),
            "tensors": reference_tensors,
            "design_condition_number": _q(float(np.linalg.cond(primary_design))),
            "equal_membership_design_condition_number": _q(float(np.linalg.cond(equal_design))),
            "design_raw_sha256": _raw_digest(primary_design.astype("<f8").tobytes()),
            "equal_membership_design_raw_sha256": _raw_digest(equal_design.astype("<f8").tobytes()),
        },
        "source_processing_ablation": {
            "measure": SOURCE_PROCESSING_ABLATION_MEASURE,
            "converged": ordinary_fit.converged,
            "iterations": ordinary_fit.iterations,
            "intensity_floor": _q(ordinary_fit.intensity_floor),
            "effect": ordinary_tensor,
            "loading_cosines": [
                _q(value) for value in _loading_cosines(primary_design, ordinary_design)
            ],
        },
        "degree_normalization_ablation": {
            "loading_cosines": [
                _q(value) for value in _loading_cosines(primary_design, no_degree_design)
            ]
        },
        "bootstrap": {
            "replicates": bootstrap_replicates,
            "resample_unit": "strict paired patient group",
            "patient_indices_or_hashes_bundled": False,
            "seed_namespace_digest": seed_namespace_digest,
            "row_digests": row_digests,
            "tensors": bootstrap_tensors,
        },
        "evaluation": evaluation,
        "digests": {
            "source_catalog_binding_digest": _digest(source_catalog_binding),
            "training_recipe_digest": recipe_digest,
            "union_feature_digest": _digest([int(value) for value in inputs.union_indices]),
            "program_inventory_digest": _digest(program_documents),
            "membership_degree_digest": _digest(degree_tensor),
            "reference_tensor_digest": _digest(reference_tensors),
            "centering_scaling_digest": _digest(
                {key: reference_tensors[key] for key in ("scale", "support", "eligible")}
            ),
            "reference_design_digest": _raw_digest(primary_design.astype("<f8").tobytes()),
            "equal_membership_design_digest": _raw_digest(equal_design.astype("<f8").tobytes()),
            "global_loading_digest": _raw_digest(
                np.ascontiguousarray(primary_design[:, 0], dtype="<f8").tobytes()
            ),
            "conditional_loading_digest": _raw_digest(
                np.ascontiguousarray(primary_design[:, 1:], dtype="<f8").tobytes()
            ),
            "fold_policy_digest": _digest(fold_policy),
            "source_processing_ablation_digest": _digest(ordinary_tensor),
            "bootstrap_seed_namespace_digest": seed_namespace_digest,
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
            "study_id": base.PDC_STUDY_ID,
            "article_doi": "10.1016/j.ccell.2023.12.015",
            "pdc_license": "CC-BY-4.0",
            "neftel_article_doi": "10.1016/j.cell.2019.06.024",
            "neftel_program_source": "exact Table S2 marker identities and ranks",
            "numpy_version": np.__version__,
        },
        "limitations": [
            "Research-use-only same-cohort bulk-protein transition concordance model.",
            (
                "The held-patient/held-marker evaluation is internal reconstruction, not "
                "external validation."
            ),
            (
                "Neftel programs were discovered in single-cell RNA; this fit does not "
                "assign cell states or fractions."
            ),
            (
                "Table S2 lacks numeric marker log-ratios, so source identities define "
                "masks rather than imported weights."
            ),
            (
                "Bulk protein program coordinates remain vulnerable to tumor-purity and "
                "tissue-origin confounding."
            ),
            (
                "Program membership does not establish pathway activation, causal "
                "evolution, or mechanism."
            ),
            (
                "Held-marker evaluation favors the prespecified equal-membership baseline "
                "over fitted conditional loadings; no individual fitted program effect is "
                "established."
            ),
            "Missingness, preprocessing, sampling, and cohort transport remain limitations.",
            (
                "Outputs are non-prescriptive and are not recurrence, outcome, or "
                "treatment predictions."
            ),
        ],
    }
    artifact["artifact_digest"] = _digest(artifact)
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
        / "longitudinal_gbm_neftel_transition"
        / "data"
        / "kncc_neftel_program_transition_model.v1.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdc-source-dir", type=Path, required=True)
    parser.add_argument("--hgnc-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=_default_output())
    parser.add_argument("--bootstrap-replicates", type=int, default=DEFAULT_BOOTSTRAP_REPLICATES)
    arguments = parser.parse_args()
    cohort = base.load_cohort(arguments.pdc_source_dir, arguments.hgnc_source)
    artifact = build_artifact(cohort, bootstrap_replicates=arguments.bootstrap_replicates)
    write_artifact(artifact, arguments.output)
    payload = arguments.output.read_bytes()
    print(f"wrote {arguments.output}")
    print(f"bytes={len(payload)}")
    print(f"sha256={hashlib.sha256(payload).hexdigest()}")
    print(f"content_digest={artifact['artifact_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ruff: noqa: C901, PLR0913, PLR0915, PLR0917, PLR2004, T201, TRY003
"""Fit the de-identified KNCC Reactome complex-transition factor model.

The importer consumes the exact, admitted PDC000514 paired protein matrix and
the separately frozen Reactome complex catalog.  Every complex is fitted with a
missing-aware, uncentered rank-one factor using deterministic alternating Huber
IRLS.  All preprocessing is refitted inside patient-grouped outer folds and
inside patient-cluster bootstrap draws.

Only coefficients, aggregate diagnostics, and aggregate evaluation metrics are
serialized.  Patient measurements, identifiers or hashes, fold assignments,
scores, residuals, predictions, and bootstrap resample indices are forbidden.
The fitted object supports research-only complex-member transition concordance;
it does not estimate assembly, activity, essentiality, stoichiometry, causality,
clinical state, or treatment response.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import itertools
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

from tools import import_kncc_longitudinal_gbm as base

MODEL_ID: Final = "kncc-reactome-complex-transition-factor-model/1.0.0"
PROFILE_ID: Final = "kncc-reactome-complex-transition/1.0.0"
SCHEMA_VERSION: Final = "glio-proteogen.kncc-reactome-complex-transition-factor-model/1.0.0"
SOURCE_SCHEMA_VERSION: Final = "glio-proteogen.kncc-reactome-complex-transition-source/1.0.0"
ARTIFACT_ROLE: Final = "de-identified fitted complex-member protein-transition concordance model"
PRIMARY_MEASURE: Final = "Unshared Log"
SOURCE_PROCESSING_ABLATION_MEASURE: Final = "Log"
OUTER_FOLDS: Final = 8
OUTER_FOLD_SALT: Final = "kncc-reactome-complex-patient-outer-v1"
HUBER_K: Final = 1.345
FACTOR_RIDGE: Final = 0.075
LOADING_RIDGE: Final = 0.025
SOLVER_DAMPING: Final = 0.8
SOLVER_MIN_STEP: Final = 2.0**-12
SOLVER_MAX_ITERATIONS: Final = 160
SOLVER_TOLERANCE: Final = 1.0e-6
SOLVER_RELATIVE_OBJECTIVE_TOLERANCE: Final = 1.0e-5
SOLVER_STABLE_PARAMETER_TOLERANCE: Final = 5.0e-3
OBJECTIVE_TOLERANCE: Final = 1.0e-12
COORDINATE_MAX_ITERATIONS: Final = 96
DEFAULT_BOOTSTRAP_REPLICATES: Final = 128
MAX_BOOTSTRAP_REPLICATES: Final = 256
PATIENT_CLUSTER_BOOTSTRAP_REPLICATES: Final = 20_000
PATIENT_CLUSTER_BOOTSTRAP_SEED: Final = 20_260_830
BOOTSTRAP_SEED_POLICY_ID: Final = "kncc-reactome-complex-bootstrap-seed/1.0.0"
QUANTIZATION_DECIMALS: Final = 10

FloatArray = npt.NDArray[np.float64]
Float32Array = npt.NDArray[np.float32]
IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class ComplexSpec:
    """Exact frozen complex projection required by the fitted model."""

    complex_index: int
    domain_id: str
    reactome_id: str
    name: str
    member_feature_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SourceCatalog:
    """Verified minimal view of the frozen source catalog."""

    artifact_bytes: int
    artifact_byte_digest: str
    content_digest: str
    profile_id: str
    complexes: tuple[ComplexSpec, ...]
    projection_digests: dict[str, str]


@dataclass(frozen=True, slots=True)
class ModelAxes:
    """Union and flattened-member axes used by fitted tensors."""

    union_feature_indices: IntArray
    union_position_by_feature: dict[int, int]
    positions_by_complex: tuple[IntArray, ...]
    slot_offsets: tuple[int, ...]
    member_slots: int


@dataclass(frozen=True, slots=True)
class AxisView:
    """Robust preprocessing values on the union feature axis."""

    center: FloatArray
    scale: FloatArray
    support: IntArray
    eligible: BoolArray
    reliability: FloatArray
    effect: FloatArray
    intensity_floor: float
    iterations: int
    converged: bool


class RankOneFit(NamedTuple):
    """Result of deterministic alternating Huber IRLS."""

    loadings: FloatArray
    coordinates: FloatArray
    iterations: int
    converged: bool
    objective_trace: tuple[float, ...]
    final_max_change: float
    backtracking_steps: int


class CoordinateFit(NamedTuple):
    coordinate: float
    iterations: int
    converged: bool


class EvaluationAccumulator(NamedTuple):
    model_absolute: list[float]
    center_absolute: list[float]
    zero_absolute: list[float]
    model_squared: list[float]
    center_squared: list[float]
    zero_squared: list[float]
    direction_correct: int
    direction_total: int


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
    if not math.isfinite(value):
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


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return cast("dict[str, object]", value)


def _records(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a record array")
    return cast("list[dict[str, object]]", value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    return value


def _member_indices(row: dict[str, object], label: str) -> tuple[int, ...]:
    for key in (
        "eligible_feature_indices",
        "member_feature_indices",
        "mapped_feature_indices",
    ):
        candidate = row.get(key)
        if candidate is not None:
            if not isinstance(candidate, list):
                raise ValueError(f"{label}.{key} must be an integer array")
            result = tuple(_integer(item, f"{label}.{key}") for item in candidate)
            break
    else:
        bindings = _records(row.get("member_bindings"), f"{label}.member_bindings")
        selected: list[int] = []
        for binding in bindings:
            if binding.get("eligible", True) is not True:
                continue
            raw = binding.get("feature_index", binding.get("parent_feature_index"))
            selected.append(_integer(raw, f"{label}.member_bindings.feature_index"))
        result = tuple(selected)
    if result != tuple(sorted(set(result))) or len(result) < 3:
        raise ValueError(f"{label} must bind at least three unique, ascending eligible features")
    return result


def load_source_catalog(path: Path | None = None) -> SourceCatalog:
    """Load, self-verify, and minimally project the frozen complex catalog."""

    source_path = _default_source() if path is None else path
    payload = source_path.read_bytes()
    document = _object(json.loads(payload), "source catalog")
    if document.get("schema_version") != SOURCE_SCHEMA_VERSION:
        raise ValueError("complex source catalog schema mismatch")
    if document.get("profile_id") != PROFILE_ID:
        raise ValueError("complex source catalog profile mismatch")
    embedded_digest = _string(document.get("artifact_digest"), "artifact_digest")
    content = dict(document)
    del content["artifact_digest"]
    if _digest(content) != embedded_digest:
        raise ValueError("complex source catalog content digest mismatch")
    rows = _records(document.get("complexes"), "complexes")
    complexes: list[ComplexSpec] = []
    for expected_index, row in enumerate(rows):
        label = f"complexes[{expected_index}]"
        index = _integer(row.get("complex_index", row.get("panel_index")), label)
        if index != expected_index:
            raise ValueError("complex source catalog indices must be contiguous")
        complexes.append(
            ComplexSpec(
                complex_index=index,
                domain_id=_string(row.get("domain_id"), f"{label}.domain_id"),
                reactome_id=_string(row.get("reactome_id"), f"{label}.reactome_id"),
                name=_string(row.get("name"), f"{label}.name"),
                member_feature_indices=_member_indices(row, label),
            )
        )
    if not complexes:
        raise ValueError("complex source catalog cannot be empty")
    ids = tuple(item.reactome_id for item in complexes)
    if len(ids) != len(set(ids)):
        raise ValueError("complex source catalog contains duplicate Reactome IDs")
    raw_projection = document.get("projection_digests", document.get("digests", {}))
    projection = _object(raw_projection, "projection_digests")
    projection_digests = {
        str(key): _string(value, f"projection_digests.{key}")
        for key, value in projection.items()
        if str(key).endswith("digest")
    }
    return SourceCatalog(
        artifact_bytes=len(payload),
        artifact_byte_digest=_raw_digest(payload),
        content_digest=embedded_digest,
        profile_id=PROFILE_ID,
        complexes=tuple(complexes),
        projection_digests=projection_digests,
    )


def _model_axes(source: SourceCatalog) -> ModelAxes:
    union = np.asarray(
        sorted(set().union(*(set(item.member_feature_indices) for item in source.complexes))),
        dtype=np.int64,
    )
    if union.size == 0:
        raise ValueError("complex model feature union cannot be empty")
    local = {int(feature): index for index, feature in enumerate(union)}
    positions = tuple(
        np.asarray([local[index] for index in item.member_feature_indices], dtype=np.int64)
        for item in source.complexes
    )
    offsets: list[int] = []
    cursor = 0
    for item in source.complexes:
        offsets.append(cursor)
        cursor += len(item.member_feature_indices)
    return ModelAxes(
        union_feature_indices=union,
        union_position_by_feature=local,
        positions_by_complex=positions,
        slot_offsets=tuple(offsets),
        member_slots=cursor,
    )


def _axis_view(delta: FloatArray, genes: tuple[str, ...]) -> AxisView:
    fit = base._fit_axis(delta, genes)
    count = delta.shape[0]
    reliability = np.sqrt(fit.support.astype(np.float64) / max(count, 1))
    reliability = np.where(fit.eligible, reliability, 0.0)
    return AxisView(
        center=fit.center,
        scale=fit.scale,
        support=fit.support,
        eligible=fit.eligible,
        reliability=reliability,
        effect=fit.effect,
        intensity_floor=fit.intensity_floor,
        iterations=fit.iterations,
        converged=fit.converged,
    )


def _huber_loss(residual: FloatArray) -> FloatArray:
    absolute = np.abs(residual)
    return np.where(
        absolute <= HUBER_K,
        0.5 * residual * residual,
        HUBER_K * (absolute - 0.5 * HUBER_K),
    )


def _huber_weight(residual: FloatArray) -> FloatArray:
    absolute = np.abs(residual)
    return np.where(
        absolute <= HUBER_K,
        1.0,
        HUBER_K / np.maximum(absolute, 1.0e-15),
    )


def _normalize_orientation(
    coordinates: FloatArray,
    loadings: FloatArray,
    source_effect: FloatArray,
) -> tuple[FloatArray, FloatArray]:
    norm = float(np.linalg.norm(loadings))
    if not math.isfinite(norm) or norm <= 1.0e-15:
        raise ValueError("rank-one loading norm is zero or non-finite")
    normalized = loadings / norm
    rescaled = coordinates * norm
    orientation = float(np.dot(normalized, source_effect))
    if orientation < 0.0 or (
        orientation == 0.0 and normalized[int(np.argmax(np.abs(normalized)))] < 0.0
    ):
        normalized = -normalized
        rescaled = -rescaled
    return rescaled, normalized


def _balance_ridge_scale(
    coordinates: FloatArray,
    loadings: FloatArray,
) -> tuple[FloatArray, FloatArray]:
    """Resolve factor/loading scale drift at the ridge-optimal reciprocal scale."""

    coordinate_energy = float(np.dot(coordinates, coordinates))
    loading_energy = float(np.dot(loadings, loadings))
    if coordinate_energy <= 1.0e-30 or loading_energy <= 1.0e-30:
        return coordinates, loadings
    scale = (LOADING_RIDGE * loading_energy / (FACTOR_RIDGE * coordinate_energy)) ** 0.25
    return coordinates * scale, loadings / scale


def _rank_objective(
    values: FloatArray,
    reliability: FloatArray,
    coordinates: FloatArray,
    loadings: FloatArray,
) -> float:
    finite = np.isfinite(values)
    prediction = coordinates[:, None] * loadings[None, :]
    residual = np.where(finite, values - prediction, 0.0)
    weighted = reliability[None, :] * _huber_loss(residual)
    evidence = float(np.where(finite, weighted, 0.0).sum())
    penalty = 0.5 * FACTOR_RIDGE * float(np.dot(coordinates, coordinates))
    penalty += 0.5 * LOADING_RIDGE * float(np.dot(loadings, loadings))
    return evidence + penalty


def _initial_loading(
    values: FloatArray,
    reliability: FloatArray,
    source_effect: FloatArray,
) -> FloatArray:
    loading = source_effect * reliability
    if float(np.linalg.norm(loading)) <= 1.0e-15:
        with np.errstate(all="ignore"):
            location = np.nanmedian(values, axis=0)
        loading = np.where(np.isfinite(location), location, 0.0) * reliability
    if float(np.linalg.norm(loading)) <= 1.0e-15:
        loading = np.where(reliability > 0.0, reliability, 0.0)
    norm = float(np.linalg.norm(loading))
    if not math.isfinite(norm) or norm <= 1.0e-15:
        raise ValueError("rank-one factor has no supported member loading")
    return loading / norm


def _coordinate_sweep(
    values: FloatArray,
    reliability: FloatArray,
    loadings: FloatArray,
    current: FloatArray,
) -> FloatArray:
    finite = np.isfinite(values)
    residual = np.where(finite, values - current[:, None] * loadings, 0.0)
    weights = _huber_weight(residual) * reliability[None, :] * finite
    numerator = np.sum(weights * loadings[None, :] * np.where(finite, values, 0.0), axis=1)
    denominator = np.sum(weights * loadings[None, :] ** 2, axis=1) + FACTOR_RIDGE
    return numerator / np.maximum(denominator, 1.0e-15)


def _loading_sweep(
    values: FloatArray,
    reliability: FloatArray,
    coordinates: FloatArray,
    current: FloatArray,
) -> FloatArray:
    finite = np.isfinite(values)
    residual = np.where(finite, values - coordinates[:, None] * current, 0.0)
    weights = _huber_weight(residual) * reliability[None, :] * finite
    numerator = np.sum(weights * coordinates[:, None] * np.where(finite, values, 0.0), axis=0)
    denominator = np.sum(weights * coordinates[:, None] ** 2, axis=0) + LOADING_RIDGE
    updated = numerator / np.maximum(denominator, 1.0e-15)
    return cast("FloatArray", np.where(reliability > 0.0, updated, 0.0))


def fit_rank_one(
    values: FloatArray,
    reliability: FloatArray,
    source_effect: FloatArray,
) -> RankOneFit:
    """Fit a deterministic robust missing-aware uncentered rank-one model."""

    if values.ndim != 2 or values.shape[1] < 3 or values.shape[0] < 3:
        raise ValueError("rank-one values must have at least three rows and members")
    if reliability.shape != (values.shape[1],) or source_effect.shape != reliability.shape:
        raise ValueError("rank-one reliability/effect shape mismatch")
    if np.any(~np.isfinite(reliability)) or np.any(reliability < 0.0):
        raise ValueError("rank-one reliability must be finite and non-negative")
    finite = np.isfinite(values)
    if np.any(finite.sum(axis=0) < 3) or np.count_nonzero(reliability > 0.0) < 3:
        raise ValueError("rank-one factor requires three supported observations per member")
    loadings = _initial_loading(values, reliability, source_effect)
    coordinates = np.zeros(values.shape[0], dtype=np.float64)
    for _ in range(8):
        coordinates = _coordinate_sweep(values, reliability, loadings, coordinates)
    coordinates, loadings = _balance_ridge_scale(coordinates, loadings)
    objective = _rank_objective(values, reliability, coordinates, loadings)
    trace = [objective]
    backtracks = 0
    final_change = math.inf
    converged = False
    iterations = 0
    for step in range(1, SOLVER_MAX_ITERATIONS + 1):
        iterations = step
        proposed_coordinates = _coordinate_sweep(values, reliability, loadings, coordinates)
        proposed_loadings = _loading_sweep(values, reliability, proposed_coordinates, loadings)
        proposed_coordinates, proposed_loadings = _balance_ridge_scale(
            proposed_coordinates, proposed_loadings
        )
        accepted = False
        damping = SOLVER_DAMPING
        next_coordinates = coordinates
        next_loadings = loadings
        next_objective = objective
        while damping >= SOLVER_MIN_STEP:
            candidate_coordinates = coordinates + damping * (proposed_coordinates - coordinates)
            candidate_loadings = loadings + damping * (proposed_loadings - loadings)
            candidate_coordinates, candidate_loadings = _balance_ridge_scale(
                candidate_coordinates, candidate_loadings
            )
            candidate_objective = _rank_objective(
                values,
                reliability,
                candidate_coordinates,
                candidate_loadings,
            )
            if candidate_objective <= objective + OBJECTIVE_TOLERANCE:
                next_coordinates = candidate_coordinates
                next_loadings = candidate_loadings
                next_objective = candidate_objective
                accepted = True
                break
            damping *= 0.5
            backtracks += 1
        if not accepted:
            break
        coordinate_change = float(np.max(np.abs(next_coordinates - coordinates)))
        loading_change = float(np.max(np.abs(next_loadings - loadings)))
        final_change = max(coordinate_change, loading_change)
        relative_drop = (objective - next_objective) / max(1.0, abs(objective))
        coordinates = next_coordinates
        loadings = next_loadings
        objective = next_objective
        trace.append(objective)
        if final_change <= SOLVER_TOLERANCE or (
            relative_drop <= SOLVER_RELATIVE_OBJECTIVE_TOLERANCE
            and final_change <= SOLVER_STABLE_PARAMETER_TOLERANCE
        ):
            converged = True
            break
    coordinates, loadings = _normalize_orientation(coordinates, loadings, source_effect)
    return RankOneFit(
        loadings=loadings,
        coordinates=coordinates,
        iterations=iterations,
        converged=converged,
        objective_trace=tuple(trace),
        final_max_change=final_change,
        backtracking_steps=backtracks,
    )


def fit_coordinate(
    values: FloatArray,
    loadings: FloatArray,
    reliability: FloatArray,
) -> CoordinateFit:
    """Infer one held-patient factor coordinate from observed member values."""

    finite = np.isfinite(values) & np.isfinite(loadings) & (reliability > 0.0)
    if int(finite.sum()) < 2:
        return CoordinateFit(coordinate=0.0, iterations=0, converged=False)
    observed = values[finite]
    active_loading = loadings[finite]
    active_reliability = reliability[finite]

    def derivative(coordinate: float) -> float:
        residual = observed - coordinate * active_loading
        clipped = np.clip(residual, -HUBER_K, HUBER_K)
        return float(
            FACTOR_RIDGE * coordinate - np.dot(active_reliability * active_loading, clipped)
        )

    magnitude = max(
        1.0,
        float(np.max(np.abs(observed))) / max(float(np.max(np.abs(active_loading))), 1.0e-12),
    )
    lower = -magnitude
    upper = magnitude
    expansions = 0
    while derivative(lower) > 0.0 or derivative(upper) < 0.0:
        lower *= 2.0
        upper *= 2.0
        expansions += 1
        if expansions >= 32:
            return CoordinateFit(
                coordinate=0.0,
                iterations=expansions,
                converged=False,
            )
    coordinate = 0.0
    for step in range(1, COORDINATE_MAX_ITERATIONS + 1):
        coordinate = 0.5 * (lower + upper)
        gradient = derivative(coordinate)
        if abs(gradient) <= SOLVER_TOLERANCE or (upper - lower <= SOLVER_TOLERANCE):
            return CoordinateFit(
                coordinate=coordinate,
                iterations=expansions + step,
                converged=True,
            )
        if gradient < 0.0:
            lower = coordinate
        else:
            upper = coordinate
    return CoordinateFit(
        coordinate=coordinate,
        iterations=expansions + COORDINATE_MAX_ITERATIONS,
        converged=False,
    )


def _recipe() -> dict[str, object]:
    return {
        "input_transition": "paired recurrent T2 minus primary T1 protein abundance",
        "primary_measure": PRIMARY_MEASURE,
        "source_processing_ablation_measure": SOURCE_PROCESSING_ABLATION_MEASURE,
        "factor_model": "missing-aware uncentered rank-one member factor",
        "standardization": (
            "divide by training-only robust member scale without subtracting the training location"
        ),
        "training_location": "iterated Huber location, retained only as a baseline",
        "training_scale": "MAD with support-adjusted lower floor",
        "minimum_training_pair_coverage": base.MIN_TRAIN_COVERAGE,
        "mad_consistency_constant": 1.4826,
        "intensity_floor_quantile": base.INTENSITY_FLOOR_QUANTILE,
        "minimum_intensity_floor": base.MIN_INTENSITY_FLOOR,
        "preprocessing_huber_k": base.HUBER_K,
        "preprocessing_max_iterations": base.HUBER_MAX_ITERATIONS,
        "preprocessing_tolerance": base.HUBER_TOLERANCE,
        "factor_solver": "deterministic alternating Huber IRLS with backtracking",
        "factor_huber_k": HUBER_K,
        "factor_ridge": FACTOR_RIDGE,
        "loading_ridge": LOADING_RIDGE,
        "ridge_scale_balance": (
            "after each alternating sweep, apply the analytic reciprocal factor/loading "
            "rescaling that minimizes their two ridge terms without changing predictions"
        ),
        "solver_damping": SOLVER_DAMPING,
        "solver_minimum_step": SOLVER_MIN_STEP,
        "solver_max_iterations": SOLVER_MAX_ITERATIONS,
        "solver_parameter_tolerance": SOLVER_TOLERANCE,
        "solver_relative_objective_tolerance": SOLVER_RELATIVE_OBJECTIVE_TOLERANCE,
        "solver_stable_parameter_tolerance": SOLVER_STABLE_PARAMETER_TOLERANCE,
        "solver_objective_acceptance_tolerance": OBJECTIVE_TOLERANCE,
        "coordinate_solver": "exact convex Huber-ridge derivative bisection",
        "coordinate_max_iterations": COORDINATE_MAX_ITERATIONS,
        "coordinate_identifiability": (
            "stored loading has Euclidean norm one; coordinate is rescaled inversely"
        ),
        "orientation": (
            "non-negative dot product with training source recurrence effect; "
            "lexical maximum-loading sign breaks exact zero ties"
        ),
        "outer_folds": OUTER_FOLDS,
        "outer_fold_salt": OUTER_FOLD_SALT,
        "outer_assignment": (
            "SHA-256 ordered patient groups followed by balanced round-robin buckets"
        ),
        "held_member_evaluation": (
            "each finite member is masked and reconstructed from at least two other "
            "finite members in a held patient"
        ),
        "evaluation_units": "training-scale standardized transition",
        "bootstrap_generator": "numpy.random.Generator(PCG64)",
        "bootstrap_seed_policy": (
            "first 64 SHA-256 bits of an explicit versioned seed-namespace digest and "
            "zero-based replicate index; the namespace binds source-file identity, "
            "complex order, complex membership, and training recipe, but excludes "
            "provenance prose"
        ),
        "bootstrap_seed_policy_id": BOOTSTRAP_SEED_POLICY_ID,
        "bootstrap_resample_unit": "strict paired patient group",
        "bootstrap_storage": "little-endian float32 flattened member-slot tensors",
        "quantization_decimals": QUANTIZATION_DECIMALS,
        "claim_ceiling": "source-cohort complex-member transition concordance only",
    }


def _union_genes(cohort: base.Cohort, axes: ModelAxes) -> tuple[str, ...]:
    if np.any(axes.union_feature_indices < 0) or np.any(
        axes.union_feature_indices >= len(cohort.genes)
    ):
        raise ValueError("complex source member index is outside the admitted feature axis")
    return tuple(cohort.genes[int(index)] for index in axes.union_feature_indices)


def _fit_complexes(
    delta: FloatArray,
    genes: tuple[str, ...],
    axes: ModelAxes,
) -> tuple[AxisView, tuple[RankOneFit, ...]]:
    axis = _axis_view(delta, genes)
    if not axis.converged:
        raise ValueError("complex-transition preprocessing did not converge")
    fits: list[RankOneFit] = []
    for positions in axes.positions_by_complex:
        values = delta[:, positions] / axis.scale[positions]
        fit = fit_rank_one(
            values,
            axis.reliability[positions],
            axis.effect[positions],
        )
        fits.append(fit)
    return axis, tuple(fits)


def _folds(groups: tuple[str, ...]) -> tuple[IntArray, ...]:
    ordered = sorted(
        range(len(groups)),
        key=lambda index: (
            hashlib.sha256(f"{OUTER_FOLD_SALT}:{groups[index]}".encode()).digest(),
            groups[index],
        ),
    )
    result = tuple(
        np.asarray(ordered[index::OUTER_FOLDS], dtype=np.int64) for index in range(OUTER_FOLDS)
    )
    if any(fold.size == 0 for fold in result):
        raise ValueError("outer-fold policy produced an empty patient group")
    return result


def _cosine(left: FloatArray, right: FloatArray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator <= 1.0e-15:
        return 0.0
    return float(np.dot(left, right) / denominator)


def _empty_accumulator() -> EvaluationAccumulator:
    return EvaluationAccumulator([], [], [], [], [], [], 0, 0)


def _summary(accumulator: EvaluationAccumulator) -> dict[str, object]:
    if not accumulator.model_absolute:
        raise ValueError("complex evaluation produced no held-member observations")
    model_absolute = np.asarray(accumulator.model_absolute, dtype=np.float64)
    center_absolute = np.asarray(accumulator.center_absolute, dtype=np.float64)
    zero_absolute = np.asarray(accumulator.zero_absolute, dtype=np.float64)
    model_squared = np.asarray(accumulator.model_squared, dtype=np.float64)
    center_squared = np.asarray(accumulator.center_squared, dtype=np.float64)
    zero_squared = np.asarray(accumulator.zero_squared, dtype=np.float64)
    model_mae = float(np.mean(model_absolute))
    center_mae = float(np.mean(center_absolute))
    zero_mae = float(np.mean(zero_absolute))
    return {
        "evaluation_count": int(model_absolute.size),
        "model_standardized_mae": _q(model_mae),
        "training_center_standardized_mae": _q(center_mae),
        "zero_transition_standardized_mae": _q(zero_mae),
        "model_standardized_rmse": _q(float(np.sqrt(np.mean(model_squared)))),
        "training_center_standardized_rmse": _q(float(np.sqrt(np.mean(center_squared)))),
        "zero_transition_standardized_rmse": _q(float(np.sqrt(np.mean(zero_squared)))),
        "relative_mae_gain_vs_training_center": _q(
            (center_mae - model_mae) / max(center_mae, 1.0e-15)
        ),
        "relative_mae_gain_vs_zero_transition": _q((zero_mae - model_mae) / max(zero_mae, 1.0e-15)),
        "direction_accuracy": _q(
            accumulator.direction_correct / max(accumulator.direction_total, 1)
        ),
        "direction_evaluation_count": accumulator.direction_total,
    }


def _append_evaluation(
    accumulator: EvaluationAccumulator,
    *,
    observed: float,
    model: float,
    center: float,
) -> EvaluationAccumulator:
    model_error = abs(observed - model)
    center_error = abs(observed - center)
    zero_error = abs(observed)
    accumulator.model_absolute.append(model_error)
    accumulator.center_absolute.append(center_error)
    accumulator.zero_absolute.append(zero_error)
    accumulator.model_squared.append(model_error * model_error)
    accumulator.center_squared.append(center_error * center_error)
    accumulator.zero_squared.append(zero_error * zero_error)
    direction_total = accumulator.direction_total
    direction_correct = accumulator.direction_correct
    if abs(observed) > 1.0e-12:
        direction_total += 1
        direction_correct += int(
            (observed > 0.0 and model > 0.0) or (observed < 0.0 and model < 0.0)
        )
    return EvaluationAccumulator(
        accumulator.model_absolute,
        accumulator.center_absolute,
        accumulator.zero_absolute,
        accumulator.model_squared,
        accumulator.center_squared,
        accumulator.zero_squared,
        direction_correct,
        direction_total,
    )


def _patient_cluster_interval(patient_gains: FloatArray) -> dict[str, object]:
    if patient_gains.size < OUTER_FOLDS or np.any(~np.isfinite(patient_gains)):
        raise ValueError("patient-cluster evaluation gains are incomplete")
    generator = np.random.default_rng(PATIENT_CLUSTER_BOOTSTRAP_SEED)
    medians = np.empty(PATIENT_CLUSTER_BOOTSTRAP_REPLICATES, dtype=np.float64)
    batch_size = 512
    for start in range(0, PATIENT_CLUSTER_BOOTSTRAP_REPLICATES, batch_size):
        count = min(batch_size, PATIENT_CLUSTER_BOOTSTRAP_REPLICATES - start)
        draw = generator.integers(
            0,
            patient_gains.size,
            size=(count, patient_gains.size),
        )
        medians[start : start + count] = np.median(patient_gains[draw], axis=1)
    return {
        "resample_unit": "strict paired patient group",
        "replicates": PATIENT_CLUSTER_BOOTSTRAP_REPLICATES,
        "seed": PATIENT_CLUSTER_BOOTSTRAP_SEED,
        "median_relative_mae_gain": _q(float(np.median(patient_gains))),
        "improved_fraction": _q(float(np.mean(patient_gains > 0.0))),
        "nominal_90_percent_interval": [
            _q(float(np.quantile(medians, 0.05))),
            _q(float(np.quantile(medians, 0.95))),
        ],
        "cluster_values_bundled": False,
        "resample_indices_bundled": False,
    }


def _evaluation(
    cohort: base.Cohort,
    source: SourceCatalog,
    axes: ModelAxes,
    union_delta: FloatArray,
    union_genes: tuple[str, ...],
    reference_fits: tuple[RankOneFit, ...],
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    folds = _folds(cohort.patient_groups)
    all_rows = np.arange(len(cohort.patient_groups), dtype=np.int64)
    aggregate = _empty_accumulator()
    per_complex = [_empty_accumulator() for _ in source.complexes]
    loading_cosines: list[list[float]] = [[] for _ in source.complexes]
    patient_model_error = np.zeros(len(cohort.patient_groups), dtype=np.float64)
    patient_center_error = np.zeros(len(cohort.patient_groups), dtype=np.float64)
    patient_evaluations = np.zeros(len(cohort.patient_groups), dtype=np.int64)
    nonconverged_preprocessing = 0
    nonconverged_factors = 0
    nonconverged_coordinates = 0
    insufficient_coordinate_support = 0

    for held in folds:
        train = np.setdiff1d(all_rows, held, assume_unique=True)
        train_axis, train_fits = _fit_complexes(
            union_delta[train],
            union_genes,
            axes,
        )
        nonconverged_preprocessing += int(not train_axis.converged)
        for complex_index, positions in enumerate(axes.positions_by_complex):
            train_fit = train_fits[complex_index]
            nonconverged_factors += int(not train_fit.converged)
            loading_cosines[complex_index].append(
                abs(_cosine(train_fit.loadings, reference_fits[complex_index].loadings))
            )
            held_values = union_delta[np.ix_(held, positions)]
            standardized = held_values / train_axis.scale[positions]
            reliability = train_axis.reliability[positions]
            center = train_axis.center[positions] / train_axis.scale[positions]
            for held_local, patient_index in enumerate(held):
                row = standardized[held_local]
                for member_index in range(row.size):
                    observed = float(row[member_index])
                    if not math.isfinite(observed) or reliability[member_index] <= 0.0:
                        continue
                    inference_values = row.copy()
                    inference_values[member_index] = np.nan
                    coordinate = fit_coordinate(
                        inference_values,
                        train_fit.loadings,
                        reliability,
                    )
                    if not coordinate.converged:
                        if coordinate.iterations == 0:
                            insufficient_coordinate_support += 1
                        else:
                            nonconverged_coordinates += 1
                        continue
                    prediction = coordinate.coordinate * train_fit.loadings[member_index]
                    aggregate = _append_evaluation(
                        aggregate,
                        observed=observed,
                        model=prediction,
                        center=float(center[member_index]),
                    )
                    per_complex[complex_index] = _append_evaluation(
                        per_complex[complex_index],
                        observed=observed,
                        model=prediction,
                        center=float(center[member_index]),
                    )
                    patient_model_error[int(patient_index)] += abs(observed - prediction)
                    patient_center_error[int(patient_index)] += abs(
                        observed - float(center[member_index])
                    )
                    patient_evaluations[int(patient_index)] += 1

    if np.any(patient_evaluations == 0):
        raise ValueError("at least one held patient has no evaluable complex member")
    patient_model_mae = patient_model_error / patient_evaluations
    patient_center_mae = patient_center_error / patient_evaluations
    patient_gain = (patient_center_mae - patient_model_mae) / np.maximum(
        patient_center_mae, 1.0e-15
    )
    aggregate_summary = _summary(aggregate)
    aggregate_summary.update(
        {
            "held_patient_count": len(cohort.patient_groups),
            "outer_folds": OUTER_FOLDS,
            "outer_fold_sizes": [int(fold.size) for fold in folds],
            "minimum_patient_evaluation_count": int(patient_evaluations.min()),
            "maximum_patient_evaluation_count": int(patient_evaluations.max()),
            "patient_cluster_bootstrap": _patient_cluster_interval(patient_gain),
            "minimum_outer_loading_cosine": _q(min(min(values) for values in loading_cosines)),
            "median_outer_loading_cosine": _q(
                float(np.median([item for values in loading_cosines for item in values]))
            ),
            "nonconvergence_counts": {
                "preprocessing": nonconverged_preprocessing,
                "factor": nonconverged_factors,
                "held_coordinate": nonconverged_coordinates,
            },
            "held_coordinate_insufficient_support_count": (insufficient_coordinate_support),
        }
    )
    complex_summaries: list[dict[str, object]] = []
    for index, accumulator in enumerate(per_complex):
        item = _summary(accumulator)
        item.update(
            {
                "minimum_loading_cosine": _q(min(loading_cosines[index])),
                "median_loading_cosine": _q(float(np.median(loading_cosines[index]))),
            }
        )
        complex_summaries.append(item)
    return aggregate_summary, tuple(complex_summaries)


def _bootstrap_seed_namespace(source: SourceCatalog, recipe_digest: str) -> str:
    """Bind bootstrap sampling to numerical source identity, not mutable prose."""

    required = (
        "source_binding_digest",
        "complex_order_digest",
        "complex_membership_digest",
    )
    missing = tuple(key for key in required if key not in source.projection_digests)
    if missing:
        raise ValueError(f"complex source catalog lacks bootstrap seed projections: {missing}")
    return _digest(
        {
            "policy_id": BOOTSTRAP_SEED_POLICY_ID,
            "profile_id": source.profile_id,
            "source_binding_digest": source.projection_digests["source_binding_digest"],
            "complex_order_digest": source.projection_digests["complex_order_digest"],
            "complex_membership_digest": source.projection_digests[
                "complex_membership_digest"
            ],
            "training_recipe_digest": recipe_digest,
        }
    )


def _bootstrap_seed(seed_namespace_digest: str, index: int) -> int:
    payload = f"{seed_namespace_digest}:complex-bootstrap:{index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _flatten_slots(
    arrays: tuple[FloatArray, ...],
    axes: ModelAxes,
) -> FloatArray:
    result = np.empty(axes.member_slots, dtype=np.float64)
    for index, values in enumerate(arrays):
        start = axes.slot_offsets[index]
        result[start : start + values.size] = values
    return result


def _bootstrap_ensemble(
    cohort: base.Cohort,
    axes: ModelAxes,
    union_delta: FloatArray,
    union_genes: tuple[str, ...],
    reference_fits: tuple[RankOneFit, ...],
    *,
    seed_namespace_digest: str,
    replicates: int,
) -> tuple[Float32Array, Float32Array, tuple[str, ...], dict[str, object]]:
    scales = np.empty((replicates, axes.member_slots), dtype=np.float32)
    loadings = np.empty_like(scales)
    row_digests: list[str] = []
    cosine_values: list[float] = []
    nonconverged = 0
    for replicate in range(replicates):
        generator = np.random.default_rng(_bootstrap_seed(seed_namespace_digest, replicate))
        rows = generator.integers(
            0,
            len(cohort.patient_groups),
            size=len(cohort.patient_groups),
        )
        axis, fits = _fit_complexes(union_delta[rows], union_genes, axes)
        nonconverged += int(not axis.converged)
        per_complex_scale = tuple(axis.scale[positions] for positions in axes.positions_by_complex)
        per_complex_loading = tuple(fit.loadings for fit in fits)
        nonconverged += sum(not fit.converged for fit in fits)
        scale_row = _flatten_slots(per_complex_scale, axes)
        loading_row = _flatten_slots(per_complex_loading, axes)
        scales[replicate] = scale_row.astype(np.float32)
        loadings[replicate] = loading_row.astype(np.float32)
        for index, fit in enumerate(fits):
            cosine_values.append(abs(_cosine(fit.loadings, reference_fits[index].loadings)))
        row_digests.append(
            _raw_digest(
                np.ascontiguousarray(
                    np.concatenate((scale_row, loading_row)), dtype="<f4"
                ).tobytes()
            )
        )
    diagnostics: dict[str, object] = {
        "nonconverged_fit_count": nonconverged,
        "minimum_loading_cosine": _q(min(cosine_values)),
        "median_loading_cosine": _q(float(np.median(cosine_values))),
    }
    return scales, loadings, tuple(row_digests), diagnostics


def _complex_records(
    source: SourceCatalog,
    axes: ModelAxes,
    primary_axis: AxisView,
    primary_fits: tuple[RankOneFit, ...],
    ordinary_axis: AxisView,
    ordinary_fits: tuple[RankOneFit, ...],
    evaluation: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for index, spec in enumerate(source.complexes):
        positions = axes.positions_by_complex[index]
        primary = primary_fits[index]
        ordinary = ordinary_fits[index]
        trace = [_q(value) for value in primary.objective_trace]
        records.append(
            {
                "complex_index": spec.complex_index,
                "domain_id": spec.domain_id,
                "reactome_id": spec.reactome_id,
                "name": spec.name,
                "member_feature_indices": list(spec.member_feature_indices),
                "member_slot_offset": axes.slot_offsets[index],
                "member_slot_count": len(spec.member_feature_indices),
                "reference": {
                    "member_centers": [_q(value) for value in primary_axis.center[positions]],
                    "member_scales": [_q(value) for value in primary_axis.scale[positions]],
                    "member_reliabilities": [
                        _q(value) for value in primary_axis.reliability[positions]
                    ],
                    "member_support": [int(value) for value in primary_axis.support[positions]],
                    "member_loadings": [_q(value) for value in primary.loadings],
                    "coordinate_normalization": {
                        "loading_l2_norm": _q(float(np.linalg.norm(primary.loadings))),
                        "loading_orientation_dot_source_effect": _q(
                            float(
                                np.dot(
                                    primary.loadings,
                                    primary_axis.effect[positions],
                                )
                            )
                        ),
                        "standardization_center_subtracted": False,
                        "coordinate_units": (
                            "training-scale standardized member-transition L2 projection"
                        ),
                    },
                    "convergence": {
                        "converged": primary.converged,
                        "iterations": primary.iterations,
                        "objective_initial": trace[0],
                        "objective_final": trace[-1],
                        "objective_monotone": all(
                            right <= left + OBJECTIVE_TOLERANCE
                            for left, right in itertools.pairwise(trace)
                        ),
                        "objective_trace": trace,
                        "objective_trace_digest": _digest(trace),
                        "final_max_parameter_change": _q(primary.final_max_change),
                        "backtracking_steps": primary.backtracking_steps,
                    },
                },
                "source_processing_ablation": {
                    "measure": SOURCE_PROCESSING_ABLATION_MEASURE,
                    "member_centers": [_q(value) for value in ordinary_axis.center[positions]],
                    "member_scales": [_q(value) for value in ordinary_axis.scale[positions]],
                    "member_reliabilities": [
                        _q(value) for value in ordinary_axis.reliability[positions]
                    ],
                    "member_loadings": [_q(value) for value in ordinary.loadings],
                    "loading_cosine_to_primary": _q(
                        abs(_cosine(primary.loadings, ordinary.loadings))
                    ),
                    "converged": ordinary.converged,
                    "iterations": ordinary.iterations,
                },
                "outer_fold_held_member_evaluation": evaluation[index],
            }
        )
    return records


def _assert_deidentified(
    artifact: dict[str, object],
    groups: tuple[str, ...],
) -> None:
    payload = _canonical_bytes(artifact)
    lower = payload.lower()
    forbidden_keys = (
        b'"patient_groups"',
        b'"patient_ids"',
        b'"patient_identifiers"',
        b'"patient_hashes"',
        b'"fold_assignments"',
        b'"fold_membership"',
        b'"bootstrap_indices"',
        b'"resample_indices"',
        b'"scores"',
        b'"residuals"',
        b'"predictions"',
    )
    if any(token in lower for token in forbidden_keys):
        raise ValueError("fitted artifact contains a forbidden patient-level field")
    if b"kncc_gbm" in lower:
        raise ValueError("fitted artifact contains a patient identifier")
    for group in groups:
        candidates = {
            group.encode("utf-8"),
            hashlib.md5(group.encode("utf-8"), usedforsecurity=False).hexdigest().encode(),
            hashlib.sha1(group.encode("utf-8"), usedforsecurity=False).hexdigest().encode(),
            hashlib.sha256(group.encode("utf-8")).hexdigest().encode(),
            hashlib.sha512(group.encode("utf-8")).hexdigest().encode(),
        }
        if any(candidate.lower() in lower for candidate in candidates):
            raise ValueError("fitted artifact contains a patient identifier or hash")


def build_artifact(
    cohort: base.Cohort,
    *,
    source_path: Path | None = None,
    bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
) -> dict[str, object]:
    """Fit and return the canonical de-identified complex factor artifact."""

    if not 1 <= bootstrap_replicates <= MAX_BOOTSTRAP_REPLICATES:
        raise ValueError("bootstrap replicate count must be between 1 and 256")
    source = load_source_catalog(source_path)
    axes = _model_axes(source)
    union_genes = _union_genes(cohort, axes)
    union_primary = np.asarray(
        cohort.primary_delta[:, axes.union_feature_indices], dtype=np.float64
    )
    union_ordinary = np.asarray(
        cohort.ordinary_delta[:, axes.union_feature_indices], dtype=np.float64
    )
    recipe = _recipe()
    recipe_digest = _digest(recipe)
    bootstrap_seed_namespace_digest = _bootstrap_seed_namespace(source, recipe_digest)
    primary_axis, primary_fits = _fit_complexes(
        union_primary,
        union_genes,
        axes,
    )
    ordinary_axis, ordinary_fits = _fit_complexes(
        union_ordinary,
        union_genes,
        axes,
    )
    evaluation, complex_evaluation = _evaluation(
        cohort,
        source,
        axes,
        union_primary,
        union_genes,
        primary_fits,
    )
    bootstrap_scale, bootstrap_loading, row_digests, bootstrap_diagnostics = _bootstrap_ensemble(
        cohort,
        axes,
        union_primary,
        union_genes,
        primary_fits,
        seed_namespace_digest=bootstrap_seed_namespace_digest,
        replicates=bootstrap_replicates,
    )
    complex_records = _complex_records(
        source,
        axes,
        primary_axis,
        primary_fits,
        ordinary_axis,
        ordinary_fits,
        complex_evaluation,
    )
    bootstrap_tensors = {
        "member_scale": _tensor(bootstrap_scale, "<f4"),
        "member_loading": _tensor(bootstrap_loading, "<f4"),
    }
    fold_policy = {
        "outer_folds": OUTER_FOLDS,
        "outer_fold_salt": OUTER_FOLD_SALT,
        "assignment": ("SHA-256 ordered patient groups followed by balanced round-robin buckets"),
        "all_preprocessing_and_loadings_refit_inside_each_outer_fold": True,
        "fold_assignments_bundled": False,
    }
    source_binding = {
        "artifact_bytes": source.artifact_bytes,
        "artifact_byte_digest": source.artifact_byte_digest,
        "content_digest": source.content_digest,
        "profile_id": source.profile_id,
        "projection_digests": source.projection_digests,
    }
    reference_loading_digest = _digest([record["reference"] for record in complex_records])
    source_processing_digest = _digest(
        [record["source_processing_ablation"] for record in complex_records]
    )
    bootstrap_digest = _digest({"tensors": bootstrap_tensors, "row_digests": row_digests})
    artifact: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "profile_id": PROFILE_ID,
        "artifact_role": ARTIFACT_ROLE,
        "source_catalog_binding": source_binding,
        "training_recipe": recipe,
        "fold_policy": fold_policy,
        "counts": {
            "source_paired_groups": len(cohort.patient_groups),
            "source_gene_features": len(cohort.genes),
            "union_features": int(axes.union_feature_indices.size),
            "complexes": len(source.complexes),
            "member_slots": axes.member_slots,
            "bootstrap_replicates": bootstrap_replicates,
        },
        "union_feature_indices": [int(value) for value in axes.union_feature_indices],
        "complexes": complex_records,
        "reference_preprocessing": {
            "measure": PRIMARY_MEASURE,
            "converged": primary_axis.converged,
            "iterations": primary_axis.iterations,
            "intensity_floor": _q(primary_axis.intensity_floor),
        },
        "source_processing_ablation": {
            "measure": SOURCE_PROCESSING_ABLATION_MEASURE,
            "converged": ordinary_axis.converged,
            "iterations": ordinary_axis.iterations,
            "intensity_floor": _q(ordinary_axis.intensity_floor),
            "minimum_loading_cosine": _q(
                min(
                    abs(_cosine(left.loadings, right.loadings))
                    for left, right in zip(primary_fits, ordinary_fits, strict=True)
                )
            ),
            "median_loading_cosine": _q(
                float(
                    np.median(
                        [
                            abs(_cosine(left.loadings, right.loadings))
                            for left, right in zip(primary_fits, ordinary_fits, strict=True)
                        ]
                    )
                )
            ),
        },
        "bootstrap": {
            "replicates": bootstrap_replicates,
            "resample_unit": "strict paired patient group",
            "seed_namespace_digest": bootstrap_seed_namespace_digest,
            "member_slot_axis": "complex order then member_feature_indices order",
            "resample_indices_bundled": False,
            "row_digests": list(row_digests),
            "tensors": bootstrap_tensors,
            "diagnostics": bootstrap_diagnostics,
        },
        "evaluation": evaluation,
        "digests": {
            "training_recipe_digest": recipe_digest,
            "bootstrap_seed_namespace_digest": bootstrap_seed_namespace_digest,
            "source_catalog_binding_digest": _digest(source_binding),
            "fold_policy_digest": _digest(fold_policy),
            "union_feature_digest": _digest([int(value) for value in axes.union_feature_indices]),
            "complex_order_digest": _digest([item.reactome_id for item in source.complexes]),
            "reference_loading_digest": reference_loading_digest,
            "source_processing_ablation_digest": source_processing_digest,
            "bootstrap_ensemble_digest": bootstrap_digest,
            "evaluation_digest": _digest(evaluation),
        },
        "privacy": {
            "patient_measurements_bundled": False,
            "patient_identifiers_or_hashes_bundled": False,
            "patient_factor_coordinates_bundled": False,
            "patient_scores_or_residuals_bundled": False,
            "fold_assignments_bundled": False,
            "bootstrap_resample_indices_bundled": False,
        },
        "provenance": {
            "study_id": "PDC000514",
            "article_doi": "10.1016/j.ccell.2023.12.015",
            "pdc_license": "CC-BY-4.0",
            "reactome_annotation_license": "CC0-1.0",
            "numpy_version": np.__version__,
        },
        "claim_boundary": {
            "supported_claim": ("source-cohort complex-member protein-transition concordance"),
            "unsupported_claims": [
                "complex assembly",
                "complex biochemical activity",
                "member essentiality",
                "stoichiometric occupancy",
                "causal mechanism",
                "clinical state",
                "treatment response",
            ],
        },
        "limitations": [
            "Research-use-only internal source-cohort concordance model.",
            (
                "Held-patient held-member reconstruction is internal evaluation, "
                "not external validation."
            ),
            (
                "Reactome membership does not establish assembly, activity, "
                "essentiality, stoichiometry, flux, or causality."
            ),
            (
                "A rank-one factor is an explicit low-rank approximation and may "
                "underrepresent multi-state or antagonistic member behavior."
            ),
            (
                "Missingness, source preprocessing, sampling, overlap between "
                "complexes, and cohort transport remain limitations."
            ),
            "Outputs are non-prescriptive and are not recurrence or treatment predictions.",
        ],
    }
    artifact["artifact_digest"] = _digest(artifact)
    _assert_deidentified(artifact, cohort.patient_groups)
    return artifact


def write_artifact(document: dict[str, object], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_canonical_bytes(document))


def _default_source() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "glio_proteogen"
        / "research"
        / "longitudinal_gbm_complex_transition"
        / "data"
        / "kncc_reactome_complex_transition_source.v1.json"
    )


def _default_output() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "glio_proteogen"
        / "research"
        / "longitudinal_gbm_complex_transition"
        / "data"
        / "kncc_reactome_complex_transition_model.v1.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdc-source-dir", type=Path, required=True)
    parser.add_argument("--hgnc-source", type=Path, required=True)
    parser.add_argument("--source-catalog", type=Path, default=_default_source())
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
        source_path=arguments.source_catalog,
        bootstrap_replicates=arguments.bootstrap_replicates,
    )
    write_artifact(artifact, arguments.output)
    payload = arguments.output.read_bytes()
    print(f"wrote {arguments.output}")
    print(f"bytes={len(payload)}")
    print(f"sha256={hashlib.sha256(payload).hexdigest()}")
    print(f"content_digest={artifact['artifact_digest']}")
    evaluation = cast("dict[str, object]", artifact["evaluation"])
    print(
        "evaluation="
        f"{evaluation['evaluation_count']} held members; "
        f"gain={evaluation['relative_mae_gain_vs_training_center']}; "
        f"direction_accuracy={evaluation['direction_accuracy']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

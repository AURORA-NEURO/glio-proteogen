"""Deterministic donor/study-shrunk Dirichlet-multinomial fitting.

The fitted study signatures have equal influence on the reported global
signature. Donor compositions enter only through per-donor, per-count
Dirichlet-multinomial losses; a study with more donors therefore supplies more
evidence for its own signature without receiving extra weight in the global
signature update.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .errors import GbmapInputError, GbmapNumericalError
from .numerics import digamma, trigamma

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

SIMPLEX_FLOOR: Final = 1.0e-12
MINIMUM_CONCENTRATION: Final = 4.0
MAXIMUM_CONCENTRATION: Final = 1.0e5
BACKGROUND_REGULARIZATION: Final = 0.01

_PROBABILITY_TOLERANCE: Final = 1.0e-10
_MAX_COUNT: Final = int(np.iinfo(np.int64).max)
_GOLDEN_RATIO_COMPLEMENT: Final = (math.sqrt(5.0) - 1.0) / 2.0
_DIRECT_RISING_FACTORIAL_LIMIT: Final = 256


@dataclass(frozen=True, slots=True)
class HierarchySolverConfiguration:
    """Locked numerical controls for one lineage hierarchy fit."""

    max_outer_iterations: int = 100
    max_study_sweeps: int = 8
    max_signature_iterations: int = 60
    max_backtracking_steps: int = 60
    initial_signature_step: float = 1.0
    maximum_signature_step: float = 64.0
    step_growth: float = 1.5
    backtracking_factor: float = 0.5
    armijo_fraction: float = 1.0e-4
    inner_l1_tolerance: float = 1.0e-10
    relative_objective_tolerance: float = 1.0e-9
    simplex_l1_tolerance: float = 1.0e-8
    kkt_tolerance: float = 1.0e-6
    objective_increase_tolerance: float = 1.0e-15
    golden_log_tolerance: float = 1.0e-7
    max_golden_iterations: int = 64

    def __post_init__(self) -> None:
        if not 1 <= self.max_outer_iterations <= 100:
            raise ValueError("hierarchy outer iterations must be between one and 100")
        integer_controls = (
            self.max_study_sweeps,
            self.max_signature_iterations,
            self.max_backtracking_steps,
            self.max_golden_iterations,
        )
        if any(value < 1 for value in integer_controls):
            raise ValueError("hierarchy iteration controls must be positive")
        positive = (
            self.initial_signature_step,
            self.maximum_signature_step,
            self.step_growth,
            self.backtracking_factor,
            self.armijo_fraction,
            self.inner_l1_tolerance,
            self.relative_objective_tolerance,
            self.simplex_l1_tolerance,
            self.kkt_tolerance,
            self.golden_log_tolerance,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("hierarchy numerical controls must be finite and positive")
        if self.maximum_signature_step < self.initial_signature_step:
            raise ValueError("maximum signature step must not be below its initial value")
        if self.step_growth <= 1.0:
            raise ValueError("hierarchy step growth must exceed one")
        if not 0.0 < self.backtracking_factor < 1.0:
            raise ValueError("hierarchy backtracking factor must lie between zero and one")
        if not 0.0 < self.armijo_fraction < 1.0:
            raise ValueError("hierarchy Armijo fraction must lie between zero and one")
        if (
            not math.isfinite(self.objective_increase_tolerance)
            or self.objective_increase_tolerance < 0.0
        ):
            raise ValueError("hierarchy objective tolerance must be finite and non-negative")


DEFAULT_HIERARCHY_CONFIGURATION: Final = HierarchySolverConfiguration()


@dataclass(frozen=True, slots=True)
class HierarchyTraceRecord:
    """Diagnostics recorded after one complete signature/concentration update."""

    iteration: int
    objective: float
    concentration: float
    relative_objective_change: float
    maximum_signature_l1_change: float
    kkt_residual: float
    signature_updates: int
    backtracking_steps: int
    concentration_search_iterations: int

    def __post_init__(self) -> None:
        finite_nonnegative = (
            self.objective,
            self.relative_objective_change,
            self.maximum_signature_l1_change,
            self.kkt_residual,
        )
        if self.iteration < 1 or any(
            not math.isfinite(value) or value < 0.0 for value in finite_nonnegative
        ):
            raise ValueError("hierarchy trace diagnostics are invalid")
        if not MINIMUM_CONCENTRATION <= self.concentration <= MAXIMUM_CONCENTRATION:
            raise ValueError("hierarchy trace concentration is outside its locked bounds")
        if (
            min(
                self.signature_updates,
                self.backtracking_steps,
                self.concentration_search_iterations,
            )
            < 0
        ):
            raise ValueError("hierarchy trace iteration counts must be non-negative")


@dataclass(frozen=True, slots=True)
class LineageHierarchyFit:
    """One immutable fitted lineage hierarchy and explicit convergence state."""

    study_keys: tuple[str, ...]
    study_signatures: FloatArray
    global_signature: FloatArray
    concentration: float
    shrinkage: float
    initial_objective: float
    objective: float
    converged: bool
    iterations: int
    kkt_residual: float
    trace: tuple[HierarchyTraceRecord, ...]

    def __post_init__(self) -> None:
        if not self.study_keys or tuple(sorted(self.study_keys)) != self.study_keys:
            raise ValueError("hierarchy study keys must be non-empty and sorted")
        if len(set(self.study_keys)) != len(self.study_keys):
            raise ValueError("hierarchy study keys must be unique")
        signatures = np.array(self.study_signatures, dtype=np.float64, copy=True, order="C")
        global_signature = np.array(self.global_signature, dtype=np.float64, copy=True)
        if signatures.ndim != 2 or signatures.shape[0] != len(self.study_keys):
            raise ValueError("hierarchy study signature dimensions are inconsistent")
        if global_signature.shape != (signatures.shape[1],):
            raise ValueError("hierarchy global signature has an inconsistent gene axis")
        if (
            not bool(np.all(np.isfinite(signatures)))
            or not bool(np.all(np.isfinite(global_signature)))
            or bool(np.any(signatures < SIMPLEX_FLOOR))
            or bool(np.any(global_signature < SIMPLEX_FLOOR))
        ):
            raise ValueError("hierarchy signatures must be finite floored probabilities")
        for row in signatures:
            if not math.isclose(
                math.fsum(float(value) for value in row),
                1.0,
                rel_tol=0.0,
                abs_tol=_PROBABILITY_TOLERANCE,
            ):
                raise ValueError("every hierarchy study signature must sum to one")
        if not math.isclose(
            math.fsum(float(value) for value in global_signature),
            1.0,
            rel_tol=0.0,
            abs_tol=_PROBABILITY_TOLERANCE,
        ):
            raise ValueError("hierarchy global signature must sum to one")
        signatures.flags.writeable = False
        global_signature.flags.writeable = False
        object.__setattr__(self, "study_signatures", signatures)
        object.__setattr__(self, "global_signature", global_signature)

        scalars = (
            self.shrinkage,
            self.initial_objective,
            self.objective,
            self.kkt_residual,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in scalars):
            raise ValueError("hierarchy fit diagnostics must be finite and non-negative")
        if not MINIMUM_CONCENTRATION <= self.concentration <= MAXIMUM_CONCENTRATION:
            raise ValueError("hierarchy concentration is outside its locked bounds")
        if self.iterations != len(self.trace):
            raise ValueError("hierarchy iteration count does not match its trace")


@dataclass(frozen=True, slots=True)
class _StudyData:
    """Precomputed immutable views for one canonical study block."""

    counts: IntArray
    counts_float: FloatArray
    totals: FloatArray


@dataclass(frozen=True, slots=True)
class _HierarchyData:
    counts: IntArray
    counts_float: FloatArray
    totals: FloatArray
    study_indices: IntArray
    study_keys: tuple[str, ...]
    studies: tuple[_StudyData, ...]
    background: FloatArray


@dataclass(frozen=True, slots=True)
class _ObjectiveCacheEntry:
    concentration: float
    signature: FloatArray
    donor_terms: tuple[float, ...]


class _HierarchyObjectiveEvaluator:
    """Reuse exact donor terms for unchanged study blocks during line search.

    A coordinate update changes one study signature at a time. Re-evaluating
    every other study's Dirichlet-multinomial terms dominated the hierarchy
    runtime, even though those terms are bit-for-bit invariant. The cache is
    deliberately one entry per study: it is bounded, local to one fit, and
    compares the complete signature plus the exact concentration before reuse.
    The final ``math.fsum`` still receives donor terms in canonical donor order.
    """

    __slots__ = ("_data", "_entries")

    def __init__(self, data: _HierarchyData) -> None:
        self._data = data
        self._entries: list[_ObjectiveCacheEntry | None] = [None] * len(data.studies)

    def evaluate(
        self,
        study_signatures: FloatArray,
        concentration: float,
        shrinkage: float,
    ) -> float:
        donor_terms: list[float] = []
        for study, block in enumerate(self._data.studies):
            signature = study_signatures[study]
            entry = self._entries[study]
            if (
                entry is None
                or entry.concentration != concentration
                or not np.array_equal(entry.signature, signature)
            ):
                entry = _ObjectiveCacheEntry(
                    concentration=concentration,
                    signature=np.array(signature, dtype=np.float64, copy=True, order="C"),
                    donor_terms=tuple(
                        _dm_per_count_nll_prevalidated(
                            block.counts[donor],
                            signature,
                            concentration,
                        )
                        for donor in range(block.counts.shape[0])
                    ),
                )
                self._entries[study] = entry
            donor_terms.extend(entry.donor_terms)
        return _objective_from_donor_terms(
            self._data,
            study_signatures,
            shrinkage,
            tuple(donor_terms),
        )


def _nonnegative_scalar(value: object, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise GbmapInputError(f"{name} must be a non-Boolean real scalar")
    converted = float(value)
    if not math.isfinite(converted) or converted < 0.0:
        raise GbmapInputError(f"{name} must be finite and non-negative")
    return converted


def _concentration(value: object) -> float:
    converted = _nonnegative_scalar(value, name="concentration")
    if not MINIMUM_CONCENTRATION <= converted <= MAXIMUM_CONCENTRATION:
        raise GbmapInputError("concentration must lie within [4, 100000]")
    return converted


def _probability_vector(values: ArrayLike, *, name: str, size: int | None = None) -> FloatArray:
    try:
        raw = np.asarray(values, dtype=object)
    except (TypeError, ValueError) as error:
        raise GbmapInputError(f"{name} must be a rectangular probability vector") from error
    if raw.ndim != 1 or raw.size < 2:
        raise GbmapInputError(f"{name} must be a vector with at least two genes")
    if size is not None and raw.size != size:
        raise GbmapInputError(f"{name} does not match the donor gene axis")
    converted: list[float] = []
    for item in raw:
        if isinstance(item, (bool, np.bool_)) or not isinstance(item, Real):
            raise GbmapInputError(f"{name} must contain non-Boolean real values")
        numeric = float(item)
        if not math.isfinite(numeric) or numeric < SIMPLEX_FLOOR:
            raise GbmapInputError(
                f"{name} must contain finite probabilities at least {SIMPLEX_FLOOR:g}"
            )
        converted.append(numeric)
    if not math.isclose(
        math.fsum(converted),
        1.0,
        rel_tol=0.0,
        abs_tol=_PROBABILITY_TOLERANCE,
    ):
        raise GbmapInputError(f"{name} must sum to one")
    return np.asarray(converted, dtype=np.float64)


def _probability_matrix(
    values: ArrayLike,
    *,
    study_count: int,
    gene_count: int,
) -> FloatArray:
    try:
        raw = np.asarray(values, dtype=object)
    except (TypeError, ValueError) as error:
        raise GbmapInputError("study signatures must form a rectangular matrix") from error
    if raw.shape != (study_count, gene_count):
        raise GbmapInputError("study signatures must have shape (studies, genes)")
    rows = [
        _probability_vector(raw[index], name="study signature", size=gene_count)
        for index in range(study_count)
    ]
    return np.ascontiguousarray(np.stack(rows), dtype=np.float64)


def _counts_matrix(values: ArrayLike) -> IntArray:
    try:
        raw = np.asarray(values, dtype=object)
    except (TypeError, ValueError) as error:
        raise GbmapInputError("donor counts must form a rectangular matrix") from error
    if raw.ndim != 2 or raw.shape[0] < 1 or raw.shape[1] < 2:
        raise GbmapInputError("donor counts must have shape (donors, at least two genes)")
    converted = np.empty(raw.shape, dtype=np.int64)
    for donor in range(raw.shape[0]):
        total = 0
        for gene in range(raw.shape[1]):
            item = raw[donor, gene]
            if isinstance(item, (float, np.floating)) and not math.isfinite(float(item)):
                raise GbmapInputError("donor counts must not contain non-finite values")
            if isinstance(item, (bool, np.bool_)) or not isinstance(item, Integral):
                raise GbmapInputError("donor counts must be exact non-Boolean integers")
            count = int(item)
            if count < 0 or count > _MAX_COUNT:
                raise GbmapInputError("donor counts must be non-negative int64 values")
            total += count
            if total > _MAX_COUNT:
                raise GbmapInputError("a donor total exceeds the supported int64 range")
            converted[donor, gene] = count
        if total == 0:
            raise GbmapInputError("every donor aggregate must have positive total count")
    return converted


def _study_keys(values: Sequence[str], *, donor_count: int) -> tuple[str, ...]:
    try:
        keys = tuple(values)
    except TypeError as error:
        raise GbmapInputError("donor study mapping must be a finite sequence") from error
    if len(keys) != donor_count:
        raise GbmapInputError("donor study mapping must have one key per donor")
    if any(not isinstance(key, str) or not key.strip() for key in keys):
        raise GbmapInputError("study keys must be non-empty strings")
    return keys


def _validated_data(
    donor_counts: ArrayLike,
    donor_studies: Sequence[str],
    background: ArrayLike,
) -> _HierarchyData:
    counts = _counts_matrix(donor_counts)
    keys_by_donor = _study_keys(donor_studies, donor_count=counts.shape[0])
    background_values = _probability_vector(
        background,
        name="background",
        size=counts.shape[1],
    )
    study_keys = tuple(sorted(set(keys_by_donor)))
    key_to_index = {key: index for index, key in enumerate(study_keys)}
    order = sorted(
        range(counts.shape[0]),
        key=lambda donor: (
            keys_by_donor[donor],
            tuple(int(value) for value in counts[donor]),
        ),
    )
    canonical_counts = np.ascontiguousarray(counts[order], dtype=np.int64)
    counts_float = canonical_counts.astype(np.float64)
    totals = np.sum(canonical_counts, axis=1, dtype=np.int64).astype(np.float64)
    indices = np.asarray(
        [key_to_index[keys_by_donor[donor]] for donor in order],
        dtype=np.int64,
    )
    studies: list[_StudyData] = []
    for study in range(len(study_keys)):
        start = int(np.searchsorted(indices, study, side="left"))
        stop = int(np.searchsorted(indices, study, side="right"))
        studies.append(
            _StudyData(
                counts=canonical_counts[start:stop],
                counts_float=counts_float[start:stop],
                totals=totals[start:stop],
            )
        )
    return _HierarchyData(
        counts=canonical_counts,
        counts_float=counts_float,
        totals=totals,
        study_indices=indices,
        study_keys=study_keys,
        studies=tuple(studies),
        background=background_values,
    )


def _floored_simplex(values: FloatArray) -> FloatArray:
    if values.ndim != 1 or values.size < 2 or not bool(np.all(np.isfinite(values))):
        raise GbmapNumericalError("cannot project an invalid hierarchy probability vector")
    clipped = np.maximum(values, 0.0)
    total = math.fsum(float(value) for value in clipped)
    if not math.isfinite(total) or total <= 0.0:
        raise GbmapNumericalError("hierarchy simplex projection has no finite mass")
    floor_mass = SIMPLEX_FLOOR * clipped.size
    projected = SIMPLEX_FLOOR + (1.0 - floor_mass) * clipped / total
    projected /= math.fsum(float(value) for value in projected)
    if bool(np.any(projected < SIMPLEX_FLOOR * (1.0 - 8.0 * np.finfo(np.float64).eps))):
        raise GbmapNumericalError("hierarchy simplex floor could not be preserved")
    return np.ascontiguousarray(projected, dtype=np.float64)


def _global_signature(
    study_signatures: FloatArray,
    background: FloatArray,
    shrinkage: float,
) -> FloatArray:
    denominator = shrinkage * study_signatures.shape[0] + BACKGROUND_REGULARIZATION
    weighted = np.asarray(
        [
            shrinkage * math.fsum(float(value) for value in study_signatures[:, gene])
            + BACKGROUND_REGULARIZATION * float(background[gene])
            for gene in range(study_signatures.shape[1])
        ],
        dtype=np.float64,
    )
    result = weighted / denominator
    result /= math.fsum(float(value) for value in result)
    return np.ascontiguousarray(result, dtype=np.float64)


def study_balanced_global_signature(
    study_signatures: ArrayLike,
    background: ArrayLike,
    shrinkage: float,
) -> FloatArray:
    """Return the closed-form equal-study global signature update."""

    raw = np.asarray(study_signatures, dtype=object)
    if raw.ndim != 2 or raw.shape[0] < 1 or raw.shape[1] < 2:
        raise GbmapInputError("study signatures must have shape (studies, at least two genes)")
    signatures = _probability_matrix(
        raw,
        study_count=raw.shape[0],
        gene_count=raw.shape[1],
    )
    background_values = _probability_vector(
        background,
        name="background",
        size=raw.shape[1],
    )
    shrinkage_value = _nonnegative_scalar(shrinkage, name="shrinkage")
    return _global_signature(signatures, background_values, shrinkage_value)


def _objective(
    data: _HierarchyData,
    study_signatures: FloatArray,
    concentration: float,
    shrinkage: float,
) -> float:
    donor_terms = tuple(
        _dm_per_count_nll_prevalidated(
            data.counts[donor],
            study_signatures[int(data.study_indices[donor])],
            concentration,
        )
        for donor in range(data.counts.shape[0])
    )
    return _objective_from_donor_terms(
        data,
        study_signatures,
        shrinkage,
        donor_terms,
    )


def _objective_from_donor_terms(
    data: _HierarchyData,
    study_signatures: FloatArray,
    shrinkage: float,
    donor_terms: tuple[float, ...],
) -> float:
    """Combine exact cached donor terms in the canonical objective order."""

    global_signature = _global_signature(study_signatures, data.background, shrinkage)
    regularization_terms: list[float] = []
    for signature in study_signatures:
        regularization_terms.extend(
            shrinkage * float(value) * math.log(float(value) / float(global_signature[gene]))
            for gene, value in enumerate(signature)
        )
    regularization_terms.extend(
        BACKGROUND_REGULARIZATION
        * float(value)
        * math.log(float(value) / float(global_signature[gene]))
        for gene, value in enumerate(data.background)
    )
    result = math.fsum((*donor_terms, *regularization_terms))
    if not math.isfinite(result):
        raise GbmapNumericalError("hierarchy objective became non-finite")
    return result


def _log_rising_factorial_prevalidated(base: float, increment: int) -> float:
    if increment <= _DIRECT_RISING_FACTORIAL_LIMIT:
        return math.fsum(math.log(base + offset) for offset in range(increment))
    return math.lgamma(base + increment) - math.lgamma(base)


def _dm_per_count_nll_prevalidated(
    counts: IntArray,
    probabilities: FloatArray,
    concentration: float,
) -> float:
    """Fast exact DM NLL for arrays validated once at the hierarchy boundary."""

    total = sum(int(value) for value in counts)
    terms = [
        math.lgamma(total + 1),
        -_log_rising_factorial_prevalidated(concentration, total),
    ]
    for count, probability in zip(counts, probabilities, strict=True):
        alpha = concentration * float(probability)
        terms.extend(
            (
                -math.lgamma(int(count) + 1),
                _log_rising_factorial_prevalidated(alpha, int(count)),
            )
        )
    result = -math.fsum(terms) / total
    if not math.isfinite(result):
        raise GbmapNumericalError("hierarchy DM objective became non-finite")
    return result


def _study_dm_gradient(
    counts: IntArray,
    probabilities: FloatArray,
    concentration: float,
) -> FloatArray:
    return _study_dm_gradient_precomputed(
        _StudyData(
            counts=counts,
            counts_float=counts.astype(np.float64),
            totals=np.sum(counts, axis=1, dtype=np.int64).astype(np.float64),
        ),
        probabilities,
        concentration,
    )


def _study_dm_gradient_precomputed(
    data: _StudyData,
    probabilities: FloatArray,
    concentration: float,
) -> FloatArray:
    alpha = concentration * probabilities
    initial = np.asarray(digamma(alpha), dtype=np.float64)
    updated = np.asarray(digamma(data.counts_float + alpha), dtype=np.float64)
    result = np.sum(
        (concentration / data.totals[:, np.newaxis]) * (initial[np.newaxis, :] - updated),
        axis=0,
        dtype=np.float64,
    )
    if not bool(np.all(np.isfinite(result))):
        raise GbmapNumericalError("hierarchy DM gradient became non-finite")
    return np.ascontiguousarray(result, dtype=np.float64)


def _study_dm_hessian_diagonal(
    counts: IntArray,
    probabilities: FloatArray,
    concentration: float,
) -> FloatArray:
    return _study_dm_hessian_diagonal_precomputed(
        _StudyData(
            counts=counts,
            counts_float=counts.astype(np.float64),
            totals=np.sum(counts, axis=1, dtype=np.int64).astype(np.float64),
        ),
        probabilities,
        concentration,
    )


def _study_dm_hessian_diagonal_precomputed(
    data: _StudyData,
    probabilities: FloatArray,
    concentration: float,
) -> FloatArray:
    alpha = concentration * probabilities
    initial = np.asarray(trigamma(alpha), dtype=np.float64)
    updated = np.asarray(trigamma(data.counts_float + alpha), dtype=np.float64)
    result = np.sum(
        (concentration * concentration / data.totals[:, np.newaxis])
        * (initial[np.newaxis, :] - updated),
        axis=0,
        dtype=np.float64,
    )
    if not bool(np.all(np.isfinite(result))):
        raise GbmapNumericalError("hierarchy DM curvature became non-finite")
    tolerance = 32.0 * np.finfo(np.float64).eps
    if bool(np.any(result < -tolerance)):
        raise GbmapNumericalError("hierarchy DM curvature lost convexity")
    result[result < 0.0] = 0.0
    return np.ascontiguousarray(result, dtype=np.float64)


def lineage_hierarchy_objective(
    donor_counts: ArrayLike,
    donor_studies: Sequence[str],
    study_signatures: ArrayLike,
    background: ArrayLike,
    *,
    concentration: float,
    shrinkage: float,
) -> float:
    """Evaluate the exact donor DM plus equal-study shrinkage objective.

    Rows of ``study_signatures`` correspond to lexicographically sorted unique
    values from ``donor_studies``.
    """

    data = _validated_data(donor_counts, donor_studies, background)
    signatures = _probability_matrix(
        study_signatures,
        study_count=len(data.study_keys),
        gene_count=data.counts.shape[1],
    )
    return _objective(
        data,
        signatures,
        _concentration(concentration),
        _nonnegative_scalar(shrinkage, name="shrinkage"),
    )


def _gradient(
    data: _HierarchyData,
    study_signatures: FloatArray,
    concentration: float,
    shrinkage: float,
) -> FloatArray:
    result = np.zeros_like(study_signatures)
    for study in range(len(data.study_keys)):
        result[study] = _study_dm_gradient_precomputed(
            data.studies[study],
            study_signatures[study],
            concentration,
        )
    if shrinkage > 0.0:
        global_signature = _global_signature(study_signatures, data.background, shrinkage)
        result += shrinkage * (np.log(study_signatures / global_signature) + 1.0)
    if not bool(np.all(np.isfinite(result))):
        raise GbmapNumericalError("hierarchy gradient became non-finite")
    return np.ascontiguousarray(result, dtype=np.float64)


def _study_gradient(
    data: _HierarchyData,
    study_signatures: FloatArray,
    study: int,
    concentration: float,
    shrinkage: float,
) -> FloatArray:
    """Return one coordinate gradient without evaluating unrelated studies."""

    result = _study_dm_gradient_precomputed(
        data.studies[study],
        study_signatures[study],
        concentration,
    )
    if shrinkage > 0.0:
        global_signature = _global_signature(study_signatures, data.background, shrinkage)
        result += shrinkage * (np.log(study_signatures[study] / global_signature) + 1.0)
    if not bool(np.all(np.isfinite(result))):
        raise GbmapNumericalError("hierarchy gradient became non-finite")
    return np.ascontiguousarray(result, dtype=np.float64)


def lineage_hierarchy_gradient(
    donor_counts: ArrayLike,
    donor_studies: Sequence[str],
    study_signatures: ArrayLike,
    background: ArrayLike,
    *,
    concentration: float,
    shrinkage: float,
) -> FloatArray:
    """Return the objective gradient with one row per sorted study key."""

    data = _validated_data(donor_counts, donor_studies, background)
    signatures = _probability_matrix(
        study_signatures,
        study_count=len(data.study_keys),
        gene_count=data.counts.shape[1],
    )
    return _gradient(
        data,
        signatures,
        _concentration(concentration),
        _nonnegative_scalar(shrinkage, name="shrinkage"),
    )


def _study_kkt_residual(
    signature: FloatArray,
    gradient: FloatArray,
) -> float:
    active = signature > SIMPLEX_FLOOR * (1.0 + 1.0e-6)
    if not bool(np.any(active)):
        return math.inf
    multiplier = float(np.mean(gradient[active], dtype=np.float64))
    active_residual = float(np.max(np.abs(gradient[active] - multiplier)))
    inactive_residual = 0.0
    if bool(np.any(~active)):
        inactive_residual = float(np.max(np.maximum(multiplier - gradient[~active], 0.0)))
    return max(active_residual, inactive_residual)


def _kkt_residual(
    data: _HierarchyData,
    signatures: FloatArray,
    concentration: float,
    shrinkage: float,
) -> float:
    gradient = _gradient(data, signatures, concentration, shrinkage)
    return max(
        _study_kkt_residual(signatures[study], gradient[study])
        for study in range(signatures.shape[0])
    )


def _initial_signatures(data: _HierarchyData) -> FloatArray:
    signatures = np.empty(
        (len(data.study_keys), data.counts.shape[1]),
        dtype=np.float64,
    )
    for study in range(len(data.study_keys)):
        donors = np.flatnonzero(data.study_indices == study)
        pseudobulk = np.asarray(
            [
                float(sum(int(data.counts[donor, gene]) for donor in donors))
                + float(data.background[gene])
                for gene in range(data.counts.shape[1])
            ],
            dtype=np.float64,
        )
        signatures[study] = _floored_simplex(pseudobulk)
    return signatures


def _method_of_moments_concentration(
    data: _HierarchyData,
    signatures: FloatArray,
) -> float:
    numerator: list[float] = []
    denominator: list[float] = []
    for donor in range(data.counts.shape[0]):
        total = sum(int(value) for value in data.counts[donor])
        if total <= 1:
            continue
        signature = signatures[int(data.study_indices[donor])]
        for gene in range(data.counts.shape[1]):
            probability = float(signature[gene])
            observed = float(data.counts[donor, gene]) / total
            binomial_variance = probability * (1.0 - probability) / total
            numerator.append((observed - probability) ** 2 - binomial_variance)
            denominator.append(probability * (1.0 - probability) * (total - 1.0) / total)
    denominator_total = math.fsum(denominator)
    if denominator_total <= 0.0:
        return MAXIMUM_CONCENTRATION
    intraclass_correlation = math.fsum(numerator) / denominator_total
    if not math.isfinite(intraclass_correlation) or intraclass_correlation <= 0.0:
        return MAXIMUM_CONCENTRATION
    estimate = 1.0 / intraclass_correlation - 1.0
    return min(max(estimate, MINIMUM_CONCENTRATION), MAXIMUM_CONCENTRATION)


def _signature_update(
    data: _HierarchyData,
    objective_evaluator: _HierarchyObjectiveEvaluator,
    signatures: FloatArray,
    study: int,
    *,
    concentration: float,
    shrinkage: float,
    objective: float,
    step: float,
    configuration: HierarchySolverConfiguration,
    cancellation: CancellationContext | None,
) -> tuple[float, float, bool, int, float]:
    checkpoint(cancellation)
    gradient = _study_gradient(
        data,
        signatures,
        study,
        concentration,
        shrinkage,
    )
    signature = signatures[study]
    curvature = _study_dm_hessian_diagonal_precomputed(
        data.studies[study],
        signature,
        concentration,
    )
    if shrinkage > 0.0:
        # This is the positive diagonal of the fixed-global KL block. The
        # reduced equal-study objective also has negative cross-study terms;
        # omitting them here yields a conservative deterministic
        # preconditioner while the exact objective controls acceptance.
        curvature += shrinkage / signature
    curvature = np.maximum(curvature, np.finfo(np.float64).eps)
    inverse_curvature = 1.0 / curvature
    multiplier = float(np.sum(gradient * inverse_curvature)) / float(np.sum(inverse_curvature))
    # Convert the equality-constrained diagonal Newton direction
    # ``-(g-lambda)/H`` into an exponentiated-gradient coordinate. Its
    # probability-weighted mean is exactly zero, and its first-order simplex
    # displacement is therefore the Newton direction itself.
    centered = (gradient - multiplier) / (curvature * signature)
    trial_step = min(step, configuration.maximum_signature_step)
    backtracking_steps = 0
    for _ in range(configuration.max_backtracking_steps):
        checkpoint(cancellation)
        exponent = np.clip(-trial_step * centered, -700.0, 700.0)
        candidate = _floored_simplex(signature * np.exp(exponent))
        direction = candidate - signature
        directional_derivative = float(np.dot(gradient, direction))
        candidate_signatures = signatures.copy()
        candidate_signatures[study] = candidate
        candidate_objective = objective_evaluator.evaluate(
            candidate_signatures,
            concentration,
            shrinkage,
        )
        armijo_bound = (
            objective
            + configuration.armijo_fraction * min(directional_derivative, 0.0)
            + configuration.objective_increase_tolerance
        )
        if candidate_objective <= armijo_bound and candidate_objective <= objective:
            change = math.fsum(float(abs(value)) for value in direction)
            signatures[study] = candidate
            return candidate_objective, trial_step, True, backtracking_steps, change
        trial_step *= configuration.backtracking_factor
        backtracking_steps += 1
    return objective, trial_step, False, backtracking_steps, 0.0


def _optimize_concentration(
    data: _HierarchyData,
    objective_evaluator: _HierarchyObjectiveEvaluator,
    signatures: FloatArray,
    *,
    shrinkage: float,
    current_concentration: float,
    current_objective: float,
    configuration: HierarchySolverConfiguration,
    cancellation: CancellationContext | None,
) -> tuple[float, float, int]:
    lower = math.log(MINIMUM_CONCENTRATION)
    upper = math.log(MAXIMUM_CONCENTRATION)
    lower_gradient, _ = _log_concentration_derivatives(
        data,
        signatures,
        MINIMUM_CONCENTRATION,
    )
    upper_gradient, _ = _log_concentration_derivatives(
        data,
        signatures,
        MAXIMUM_CONCENTRATION,
    )
    current = min(max(math.log(current_concentration), lower), upper)
    iterations = 0

    if lower_gradient < 0.0 < upper_gradient:
        for _ in range(configuration.max_golden_iterations):
            checkpoint(cancellation)
            iterations += 1
            concentration = _bounded_concentration_from_log(current)
            gradient, curvature = _log_concentration_derivatives(
                data,
                signatures,
                concentration,
            )
            if gradient < 0.0:
                lower = current
            else:
                upper = current
            if upper - lower <= configuration.golden_log_tolerance:
                break
            candidate = (
                current - gradient / curvature
                if math.isfinite(curvature) and curvature > 0.0
                else math.nan
            )
            if not math.isfinite(candidate) or not lower < candidate < upper:
                candidate = 0.5 * (lower + upper)
            if abs(candidate - current) <= configuration.golden_log_tolerance:
                current = candidate
                break
            current = candidate
    elif lower_gradient >= 0.0:
        current = lower
    else:
        current = upper

    candidate_logs = tuple(
        sorted(
            {
                math.log(current_concentration),
                math.log(MINIMUM_CONCENTRATION),
                math.log(MAXIMUM_CONCENTRATION),
                current,
                lower,
                upper,
                0.5 * (lower + upper),
            }
        )
    )
    candidates = [
        (
            _bounded_concentration_from_log(log_concentration),
            current_objective
            if math.isclose(
                log_concentration,
                math.log(current_concentration),
                rel_tol=0.0,
                abs_tol=1.0e-15,
            )
            else objective_evaluator.evaluate(
                signatures,
                _bounded_concentration_from_log(log_concentration),
                shrinkage,
            ),
        )
        for log_concentration in candidate_logs
    ]
    best = min(
        candidates,
        key=lambda item: (
            item[1],
            abs(math.log(item[0] / current_concentration)),
            item[0],
        ),
    )
    return best[0], best[1], iterations


def _bounded_concentration_from_log(value: float) -> float:
    return min(max(math.exp(value), MINIMUM_CONCENTRATION), MAXIMUM_CONCENTRATION)


def _log_concentration_derivatives(
    data: _HierarchyData,
    signatures: FloatArray,
    concentration: float,
) -> tuple[float, float]:
    """Return first/second NLL derivatives in log-concentration coordinates."""

    probabilities = signatures[data.study_indices]
    counts = data.counts_float
    totals = data.totals
    alpha = concentration * probabilities
    log_likelihood_gradient = (
        float(digamma(concentration))
        - np.asarray(digamma(totals + concentration), dtype=np.float64)
        + np.sum(
            probabilities
            * (
                np.asarray(digamma(counts + alpha), dtype=np.float64)
                - np.asarray(digamma(alpha), dtype=np.float64)
            ),
            axis=1,
            dtype=np.float64,
        )
    )
    log_likelihood_curvature = (
        float(trigamma(concentration))
        - np.asarray(trigamma(totals + concentration), dtype=np.float64)
        + np.sum(
            probabilities
            * probabilities
            * (
                np.asarray(trigamma(counts + alpha), dtype=np.float64)
                - np.asarray(trigamma(alpha), dtype=np.float64)
            ),
            axis=1,
            dtype=np.float64,
        )
    )
    nll_gradient = -math.fsum(
        float(value / total) for value, total in zip(log_likelihood_gradient, totals, strict=True)
    )
    nll_curvature = -math.fsum(
        float(value / total) for value, total in zip(log_likelihood_curvature, totals, strict=True)
    )
    log_gradient = concentration * nll_gradient
    log_curvature = concentration * nll_gradient + concentration * concentration * nll_curvature
    if not math.isfinite(log_gradient) or not math.isfinite(log_curvature):
        raise GbmapNumericalError("hierarchy concentration derivatives became non-finite")
    return log_gradient, log_curvature


def fit_lineage_hierarchy(
    donor_counts: ArrayLike,
    donor_studies: Sequence[str],
    background: ArrayLike,
    *,
    shrinkage: float,
    configuration: HierarchySolverConfiguration = DEFAULT_HIERARCHY_CONFIGURATION,
    cancellation: CancellationContext | None = None,
) -> LineageHierarchyFit:
    """Fit one lineage's study signatures and bounded shared concentration."""

    checkpoint(cancellation)
    if not isinstance(configuration, HierarchySolverConfiguration):
        raise TypeError("configuration must be a HierarchySolverConfiguration")
    data = _validated_data(donor_counts, donor_studies, background)
    shrinkage_value = _nonnegative_scalar(shrinkage, name="shrinkage")
    signatures = _initial_signatures(data)
    concentration = _method_of_moments_concentration(data, signatures)
    objective_evaluator = _HierarchyObjectiveEvaluator(data)
    objective = objective_evaluator.evaluate(
        signatures,
        concentration,
        shrinkage_value,
    )
    initial_objective = objective
    trace: list[HierarchyTraceRecord] = []
    steps = np.full(
        len(data.study_keys),
        configuration.initial_signature_step,
        dtype=np.float64,
    )
    converged = False
    kkt_residual = _kkt_residual(data, signatures, concentration, shrinkage_value)

    for iteration in range(1, configuration.max_outer_iterations + 1):
        checkpoint(cancellation)
        # Concentration is re-optimized after every outer pass, changing the
        # curvature of every study block.  Reusing a step collapsed under the
        # previous concentration can make later passes advance only at machine
        # precision, so each new block cycle restarts from the locked step and
        # lets monotone backtracking re-establish the safe local scale.
        steps.fill(configuration.initial_signature_step)
        baseline_objective = objective
        baseline_signatures = signatures.copy()
        total_updates = 0
        total_backtracking = 0

        for _ in range(configuration.max_study_sweeps):
            sweep_updates = 0
            maximum_sweep_change = 0.0
            for study in range(len(data.study_keys)):
                for _ in range(configuration.max_signature_iterations):
                    (
                        objective,
                        accepted_step,
                        accepted,
                        backtracking_steps,
                        l1_change,
                    ) = _signature_update(
                        data,
                        objective_evaluator,
                        signatures,
                        study,
                        concentration=concentration,
                        shrinkage=shrinkage_value,
                        objective=objective,
                        step=float(steps[study]),
                        configuration=configuration,
                        cancellation=cancellation,
                    )
                    total_backtracking += backtracking_steps
                    if not accepted:
                        # A line search can reach floating-point resolution after a
                        # concentration update even while another study block is
                        # still off its KKT point. Retaining that sub-epsilon step
                        # permanently would freeze all later outer iterations.
                        steps[study] = configuration.initial_signature_step
                        break
                    total_updates += 1
                    sweep_updates += 1
                    maximum_sweep_change = max(maximum_sweep_change, l1_change)
                    steps[study] = min(
                        configuration.maximum_signature_step,
                        accepted_step * configuration.step_growth,
                    )
                    gradient = _study_gradient(
                        data,
                        signatures,
                        study,
                        concentration,
                        shrinkage_value,
                    )
                    if (
                        l1_change <= configuration.inner_l1_tolerance
                        and _study_kkt_residual(signatures[study], gradient)
                        <= configuration.kkt_tolerance
                    ):
                        break
            if sweep_updates == 0:
                break
            if (
                maximum_sweep_change <= configuration.inner_l1_tolerance
                and _kkt_residual(data, signatures, concentration, shrinkage_value)
                <= configuration.kkt_tolerance
            ):
                break

        concentration, objective, concentration_iterations = _optimize_concentration(
            data,
            objective_evaluator,
            signatures,
            shrinkage=shrinkage_value,
            current_concentration=concentration,
            current_objective=objective,
            configuration=configuration,
            cancellation=cancellation,
        )
        if objective > baseline_objective + configuration.objective_increase_tolerance:
            raise GbmapNumericalError("hierarchy objective increased beyond tolerance")
        relative_change = abs(baseline_objective - objective) / max(
            1.0,
            abs(baseline_objective),
        )
        maximum_l1_change = max(
            math.fsum(float(abs(value)) for value in signatures[study] - baseline_signatures[study])
            for study in range(signatures.shape[0])
        )
        kkt_residual = _kkt_residual(
            data,
            signatures,
            concentration,
            shrinkage_value,
        )
        trace.append(
            HierarchyTraceRecord(
                iteration=iteration,
                objective=objective,
                concentration=concentration,
                relative_objective_change=relative_change,
                maximum_signature_l1_change=maximum_l1_change,
                kkt_residual=kkt_residual,
                signature_updates=total_updates,
                backtracking_steps=total_backtracking,
                concentration_search_iterations=concentration_iterations,
            )
        )
        if (
            relative_change <= configuration.relative_objective_tolerance
            and maximum_l1_change <= configuration.simplex_l1_tolerance
            and kkt_residual <= configuration.kkt_tolerance
        ):
            converged = True
            break

    global_signature = _global_signature(signatures, data.background, shrinkage_value)
    return LineageHierarchyFit(
        study_keys=data.study_keys,
        study_signatures=signatures,
        global_signature=global_signature,
        concentration=concentration,
        shrinkage=shrinkage_value,
        initial_objective=initial_objective,
        objective=objective,
        converged=converged,
        iterations=len(trace),
        kkt_residual=kkt_residual,
        trace=tuple(trace),
    )


def verify_hierarchy_trace(
    fit: object,
    *,
    tolerance: float = 1.0e-10,
) -> bool:
    """Verify objective monotonicity and final diagnostic consistency."""

    if not isinstance(fit, LineageHierarchyFit):
        return False
    if not math.isfinite(tolerance) or tolerance < 0.0:
        return False
    previous = fit.initial_objective
    for expected_iteration, record in enumerate(fit.trace, start=1):
        if record.iteration != expected_iteration or record.objective > previous + tolerance:
            return False
        previous = record.objective
    return (
        fit.iterations == len(fit.trace)
        and math.isclose(fit.objective, previous, rel_tol=0.0, abs_tol=tolerance)
        and (
            not fit.trace
            or math.isclose(
                fit.kkt_residual,
                fit.trace[-1].kkt_residual,
                rel_tol=0.0,
                abs_tol=tolerance,
            )
        )
    )


__all__ = [
    "BACKGROUND_REGULARIZATION",
    "DEFAULT_HIERARCHY_CONFIGURATION",
    "MAXIMUM_CONCENTRATION",
    "MINIMUM_CONCENTRATION",
    "SIMPLEX_FLOOR",
    "HierarchySolverConfiguration",
    "HierarchyTraceRecord",
    "LineageHierarchyFit",
    "fit_lineage_hierarchy",
    "lineage_hierarchy_gradient",
    "lineage_hierarchy_objective",
    "study_balanced_global_signature",
    "verify_hierarchy_trace",
]

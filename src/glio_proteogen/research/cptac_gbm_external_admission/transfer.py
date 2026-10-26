"""Frozen source-only fitting and conditional raw-assay provider-transfer stress.

This profile measures errors across historically different processing systems.
It does not establish aligned biological validation or propagate training-fit
uncertainty. External values cannot participate in model fitting or selection.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from math import ceil, isfinite, sqrt
from typing import Final, NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    nested_selection as nested,
)

PROFILE_ID: Final = "cptac-gbm-raw-assay-provider-transfer-stress/1.0.0"
EXTERNAL_MINIMUM: Final = 48
BOOTSTRAP_REPLICATES: Final = 128
BOOTSTRAP_REQUIRED: Final = 103
CANDIDATE_ORDER: Final = nested.CANDIDATE_ORDER
FloatArray = npt.NDArray[np.float64]
FoldArray = npt.NDArray[np.int8]


@dataclass(frozen=True, slots=True)
class FinalSelectionEvidence:
    candidate: str
    eligible: bool
    source_oof_count: int
    source_oof_mae: float | None


@dataclass(frozen=True, slots=True)
class FinalFitEvidence:
    candidate: str
    available: bool
    iterations: int | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class SourceFitReceipt:
    profile_id: str
    accepted: bool
    complete_count: int
    common_oof_count: int
    valid_outer_folds: int
    selected_candidate: str | None
    selection_evidence: tuple[FinalSelectionEvidence, ...]
    nested_point_summary: nested.NestedPointSummary | None
    fold_trace: tuple[nested.OuterSelectionTrace, ...]
    final_fit_iterations: tuple[int | None, ...]
    failure_reason: str | None
    final_fits: tuple[FinalFitEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class _FrozenPredictor:
    candidate: str
    median: float | None = field(repr=False)
    center: tuple[float, ...] = field(repr=False)
    scale: tuple[float, ...] = field(repr=False)
    beta: tuple[float, ...] = field(repr=False)
    y_center: float = field(repr=False)
    y_scale: float = field(repr=False)

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient fitted coefficients cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient fitted coefficients cannot be serialized")

    def predict(self, cnv: FloatArray, rna: FloatArray) -> FloatArray:
        if self.median is not None:
            return np.full(len(cnv), self.median, dtype=np.float64)
        x = (
            np.column_stack((rna, cnv))
            if self.candidate == "full"
            else (rna if self.candidate == "rna_only" else cnv)[:, None]
        )
        standardized = (x - np.asarray(self.center)) / np.asarray(self.scale)
        design = np.column_stack((np.ones(len(x)), standardized))
        return np.asarray(self.y_center + self.y_scale * (design @ np.asarray(self.beta)))


@dataclass(frozen=True, slots=True)
class FrozenSourceGeneFit:
    """Private transient predictors with an explicitly separate aggregate receipt."""

    receipt: SourceFitReceipt
    _predictors: tuple[_FrozenPredictor, ...] = field(repr=False)

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient source predictors cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient source predictors cannot be serialized")


@dataclass(frozen=True, slots=True)
class TransferMetrics:
    candidate: str
    observed_count: int
    mae: float
    rmse: float
    r2_vs_source_training_median: float | None


@dataclass(frozen=True, slots=True)
class ConditionalInterval:
    point_estimate: float
    lower: float
    upper: float
    confidence_level: float
    replicates: int


@dataclass(frozen=True, slots=True)
class ConditionalMetricIntervals:
    candidate: str
    mae: ConditionalInterval
    rmse: ConditionalInterval
    r2_vs_source_training_median: ConditionalInterval | None


@dataclass(frozen=True, slots=True)
class ConditionalUncertainty:
    seed: int
    replicates_requested: int
    replicates_successful: int
    replicates_required: int
    primary_full_minus_cnv_mae: ConditionalInterval
    secondary_selected_minus_full_mae: ConditionalInterval
    metrics: tuple[ConditionalMetricIntervals, ...]
    training_refitted: bool = False
    selection_repeated: bool = False
    training_uncertainty_available: bool = False
    interval_scope: str = "external patient sampling conditional on frozen source fit"


@dataclass(frozen=True, slots=True)
class TransferGeneResult:
    profile_id: str
    request_digest: str
    source: SourceFitReceipt
    accepted: bool
    external_complete_count: int
    external_common_comparison_count: int
    external_minimum: int
    point_metrics: tuple[TransferMetrics, ...]
    primary_full_minus_cnv_mae: float | None
    secondary_selected_minus_full_mae: float | None
    uncertainty: ConditionalUncertainty | None
    failure_reason: str | None
    aligned_external_validation: bool = False
    clinical_validation: bool = False
    default_promotion: bool = False


def deterministic_patient_folds(patient_keys: tuple[str, ...]) -> FoldArray:
    """Hash-sort unique source patient keys, then round-robin to five folds.

    The caller owns source-only provenance and group identity. Patient keys are
    never returned; no outcome or external measurement enters this assignment.
    """
    if type(patient_keys) is not tuple or not 60 <= len(patient_keys) <= 10_000:
        raise ValueError("source patient keys must be a bounded tuple of at least60 groups")
    if any(
        type(key) is not str
        or not 1 <= len(key) <= 256
        or not key.isascii()
        or any(ord(char) < 33 or ord(char) > 126 for char in key)
        for key in patient_keys
    ):
        raise ValueError("source patient keys must be bounded printable ASCII identifiers")
    if len(set(patient_keys)) != len(patient_keys):
        raise ValueError("each source patient must have exactly one observation")
    order = sorted(
        range(len(patient_keys)),
        key=lambda index: (
            hashlib.sha256(patient_keys[index].encode()).digest(),
            patient_keys[index],
        ),
    )
    folds = np.empty(len(patient_keys), dtype=np.int8)
    for position, index in enumerate(order):
        folds[index] = position % 5
    return np.frombuffer(folds.tobytes(), dtype=np.int8)


def _freeze(attempt: nested.CandidateFit) -> _FrozenPredictor:
    if attempt.median is not None:
        return _FrozenPredictor(attempt.candidate, attempt.median, (), (), (), 0.0, 1.0)
    model = attempt.model
    if model is None or not attempt.available:
        raise ValueError("only available source predictors can be frozen")
    return _FrozenPredictor(
        attempt.candidate,
        None,
        tuple(float(value) for value in model.x_center),
        tuple(float(value) for value in model.x_scale),
        tuple(float(value) for value in model.beta),
        model.y_center,
        model.y_scale,
    )


def fit_source_gene(
    cnv: object, rna: object, protein: object, folds: object
) -> FrozenSourceGeneFit:
    """Fit without accepting any external features, outcomes, IDs or statistics."""
    arrays = nested._validated_inputs(cnv, rna, protein, folds)
    cnv_values, rna_values, protein_values, _fold_values = arrays
    point = nested.nested_point_fit(*arrays)
    complete = np.isfinite(cnv_values) & np.isfinite(rna_values) & np.isfinite(protein_values)
    evidence = tuple(
        FinalSelectionEvidence(
            candidate,
            bool(np.any(complete)) and bool(np.all(np.isfinite(prediction[complete]))),
            int(np.sum(np.isfinite(prediction[complete]))),
            float(np.mean(np.abs(protein_values[complete] - prediction[complete])))
            if bool(np.any(complete)) and bool(np.all(np.isfinite(prediction[complete])))
            else None,
        )
        for candidate, prediction in zip(CANDIDATE_ORDER, point.fixed_predictions, strict=True)
    )
    reason = None
    selected: str | None = None
    predictors: tuple[_FrozenPredictor, ...] = ()
    iterations: tuple[int | None, ...] = ()
    final_fits: tuple[FinalFitEvidence, ...] = ()
    if not point.accepted:
        reason = "source nested support, numerical or null-variation gates failed"
    elif not all(item.eligible and item.source_oof_mae is not None for item in evidence):
        reason = "all-five-fold common source OOF selection support unavailable"
    else:
        selected = min(
            evidence,
            key=lambda item: (
                item.source_oof_mae if item.source_oof_mae is not None else float("inf"),
                CANDIDATE_ORDER.index(item.candidate),
            ),
        ).candidate
        attempts = tuple(
            nested._fit_candidate(
                candidate,
                cnv_values[complete],
                rna_values[complete],
                protein_values[complete],
                outer_fold=-1,
                inner_fold=None,
            )
            for candidate in CANDIDATE_ORDER
        )
        iterations = tuple(
            None if item.model is None else item.model.iterations for item in attempts
        )
        final_fits = tuple(
            FinalFitEvidence(item.candidate, item.available, iteration, item.failure_reason)
            for item, iteration in zip(attempts, iterations, strict=True)
        )
        if not all(item.available for item in attempts):
            reason = "one or more full-source fixed candidate refits unavailable"
        else:
            predictors = tuple(_freeze(item) for item in attempts)
    receipt = SourceFitReceipt(
        PROFILE_ID,
        reason is None,
        int(complete.sum()),
        point.common_oof_count,
        sum(trace.comparison_accepted for trace in point.fold_trace),
        selected,
        evidence,
        point.summary,
        point.fold_trace,
        iterations,
        reason,
        final_fits,
    )
    return FrozenSourceGeneFit(receipt, predictors)


def _external_arrays(cnv: object, rna: object, protein: object) -> tuple[FloatArray, ...]:
    arrays = []
    for value in (cnv, rna, protein):
        if type(value) is not np.ndarray or value.dtype not in (
            np.dtype("float32"),
            np.dtype("float64"),
        ):
            raise TypeError("external inputs must be exact floating NumPy arrays")
        if value.ndim != 1 or not 1 <= len(value) <= 10_000:
            raise ValueError("external inputs must be bounded one-dimensional vectors")
        if bool(np.any(np.isinf(value))) or bool(
            np.any(np.abs(value[np.isfinite(value)]) > nested.MAX_ABSOLUTE_INPUT)
        ):
            raise ValueError("external inputs exceed the finite magnitude contract")
        arrays.append(np.array(value, dtype=np.float64, copy=True))
    if len({len(value) for value in arrays}) != 1:
        raise ValueError("external assay vectors must be aligned")
    return tuple(arrays)


def _metrics(
    candidate: str, truth: FloatArray, prediction: FloatArray, median: float
) -> TransferMetrics:
    residual = truth - prediction
    null_residual = truth - median
    # Extreme corrupted predictors must produce a sanitized metric abstention,
    # without a NumPy warning containing private execution context.
    with np.errstate(over="ignore", invalid="ignore"):
        sse = float(np.dot(residual, residual))
        null_sse = float(np.dot(null_residual, null_residual))
    return TransferMetrics(
        candidate,
        len(truth),
        float(np.mean(np.abs(residual))),
        sqrt(sse / len(truth)),
        1.0 - sse / null_sse if null_sse > 1e-12 else None,
    )


def _interval(samples: list[float], point: float) -> ConditionalInterval:
    ordered = sorted(samples)
    count = len(ordered)
    if count < BOOTSTRAP_REQUIRED or not all(isfinite(value) for value in ordered):
        raise ValueError("conditional intervals require sufficient finite paired replicates")
    return ConditionalInterval(
        point, ordered[max(1, ceil(count * 0.05)) - 1], ordered[ceil(count * 0.95) - 1], 0.9, count
    )


def _bootstrap(
    truth: FloatArray,
    predictions: tuple[FloatArray, ...],
    median: float,
    point: tuple[TransferMetrics, ...],
    digest: str,
) -> ConditionalUncertainty | None:
    seed = int.from_bytes(
        hashlib.sha256((PROFILE_ID + ":external-paired:" + digest).encode()).digest()[:8], "big"
    )
    rng = np.random.default_rng(seed)
    samples: tuple[tuple[list[float], list[float], list[float]], ...] = tuple(
        ([], [], []) for _ in point
    )
    primary: list[float] = []
    secondary: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        indices = rng.integers(0, len(truth), size=len(truth))
        metrics = tuple(
            _metrics(item.candidate, truth[indices], prediction[indices], median)
            for item, prediction in zip(point, predictions, strict=True)
        )
        if not all(isfinite(item.mae) and isfinite(item.rmse) for item in metrics):
            continue
        primary.append(metrics[3].mae - metrics[2].mae)
        secondary.append(metrics[4].mae - metrics[3].mae)
        for item, (mae, rmse, r2) in zip(metrics, samples, strict=True):
            mae.append(item.mae)
            rmse.append(item.rmse)
            if item.r2_vs_source_training_median is not None and isfinite(
                item.r2_vs_source_training_median
            ):
                r2.append(item.r2_vs_source_training_median)
    if len(primary) < BOOTSTRAP_REQUIRED:
        return None
    return ConditionalUncertainty(
        seed,
        BOOTSTRAP_REPLICATES,
        len(primary),
        BOOTSTRAP_REQUIRED,
        _interval(primary, point[3].mae - point[2].mae),
        _interval(secondary, point[4].mae - point[3].mae),
        tuple(
            ConditionalMetricIntervals(
                item.candidate,
                _interval(mae, item.mae),
                _interval(rmse, item.rmse),
                _interval(r2, item.r2_vs_source_training_median)
                if len(r2) >= BOOTSTRAP_REQUIRED and item.r2_vs_source_training_median is not None
                else None,
            )
            for item, (mae, rmse, r2) in zip(point, samples, strict=True)
        ),
    )


def evaluate_external_gene(
    source: FrozenSourceGeneFit, cnv: object, rna: object, protein: object, *, request_digest: str
) -> TransferGeneResult:
    """Score identical complete external patients after source fitting is frozen.

    One observation per patient is required by the plan. Resampling uses the
    same patient indices for all fixed models and the selected policy.
    """
    if not isinstance(source, FrozenSourceGeneFit):
        raise TypeError("external evaluation requires a frozen source fit")
    if (
        type(request_digest) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", request_digest) is None
    ):
        raise ValueError("a canonical request digest is required")
    cnv_values, rna_values, protein_values = _external_arrays(cnv, rna, protein)
    complete = np.isfinite(cnv_values) & np.isfinite(rna_values) & np.isfinite(protein_values)
    count = int(complete.sum())
    reason = (
        source.receipt.failure_reason or "source fit was not accepted"
        if not source.receipt.accepted
        else None
    )
    metrics: tuple[TransferMetrics, ...] = ()
    uncertainty = None
    primary = secondary = None
    common_count = 0
    if reason is None and count < EXTERNAL_MINIMUM:
        reason = "external common complete-case minimum48 not reached"
    if reason is None:
        if (
            len(source._predictors) != len(CANDIDATE_ORDER)
            or tuple(item.candidate for item in source._predictors) != CANDIDATE_ORDER
            or source.receipt.selected_candidate not in CANDIDATE_ORDER
        ):
            raise ValueError("frozen source predictor contract is incomplete")
        fixed = tuple(
            item.predict(cnv_values[complete], rna_values[complete]) for item in source._predictors
        )
        selected_index = CANDIDATE_ORDER.index(source.receipt.selected_candidate)
        predictions = (*fixed, fixed[selected_index])
        if not all(bool(np.all(np.isfinite(values))) for values in predictions):
            reason = "non-finite external prediction; no model-specific observation deletion"
        else:
            common_count = count
            median = source._predictors[0].median
            if median is None:
                raise ValueError("source training-median predictor is unavailable")
            metrics = tuple(
                _metrics(candidate, protein_values[complete], values, median)
                for candidate, values in zip(
                    (*CANDIDATE_ORDER, "selected_policy"), predictions, strict=True
                )
            )
            if not all(
                isfinite(item.mae)
                and isfinite(item.rmse)
                and (
                    item.r2_vs_source_training_median is None
                    or isfinite(item.r2_vs_source_training_median)
                )
                for item in metrics
            ):
                reason = "non-finite external metric"
                metrics = ()
            else:
                primary = metrics[3].mae - metrics[2].mae
                secondary = metrics[4].mae - metrics[3].mae
                uncertainty = _bootstrap(
                    protein_values[complete], predictions, median, metrics, request_digest
                )
                if uncertainty is None:
                    reason = "conditional paired bootstrap support below103of128"
    return TransferGeneResult(
        PROFILE_ID,
        request_digest,
        source.receipt,
        reason is None,
        count,
        common_count,
        EXTERNAL_MINIMUM,
        metrics,
        primary,
        secondary,
        uncertainty,
        reason,
    )

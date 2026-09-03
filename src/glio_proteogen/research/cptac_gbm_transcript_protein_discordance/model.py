"""Cross-fitted CPTAC-GBM transcript--protein discordance model core.

This module contains no bundled model and performs no biological classification.
It fits deterministic, patient-grouped robust regressions to an in-memory cohort.
Every value-dependent transform is learned inside an outer training fold through
the shared :func:`fit_huber` implementation.  A request digest affects only the
patient bootstrap seed; it never contributes to a point prediction or coefficient.

The returned development fit deliberately retains exact out-of-fold arrays for
scientific evaluation.  Those arrays are backed by immutable bytes, excluded from
representations, and reject pickle serialization.  They must not be placed in a
runtime artifact or API response.  Only ``DiscordanceAggregateSummary`` is intended
as input to a future de-identified artifact contract.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Final, NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.cptac_gbm_cis_dosage.model import RobustFit, fit_huber

FOLD_COUNT: Final = 5
DEFAULT_BOOTSTRAP_REPLICATES: Final = 128
DEFAULT_MINIMUM_TRAIN_COMPLETE: Final = 48
DEFAULT_MINIMUM_TEST_COMPLETE: Final = 3
DEFAULT_MINIMUM_VALID_FOLDS: Final = 4
DEFAULT_MINIMUM_OOF: Final = 60
DEFAULT_MINIMUM_BOOTSTRAP_SUCCESS_FRACTION: Final = 0.80
INTERVAL_LEVEL: Final = 0.90
QUANTIZATION_DECIMALS: Final = 8
MAX_BOOTSTRAP_REPLICATES: Final = 256
MAX_PATIENT_GROUPS: Final = 10_000

_ROBUST_SCALE_FACTOR: Final = 1.4826
_NUMERICAL_ZERO: Final = 1e-12
_SLOPE_ZERO: Final = 1e-10
_BOOTSTRAP_CONTEXT: Final = b"cptac-gbm-transcript-protein-discordance|patient-bootstrap-v1"
_SHA256_PATTERN: Final = re.compile(r"sha256:[0-9a-f]{64}\Z")

FloatArray = npt.NDArray[np.float64]
InputFloatArray = npt.NDArray[np.float32] | npt.NDArray[np.float64]
FoldArray = npt.NDArray[np.int8]
IndexArray = npt.NDArray[np.int64]


def _exact_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an exact integer")
    return value


def _exact_bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be an exact Boolean")
    return value


def _finite(value: float, field_name: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError(f"{field_name} must be a finite float")
    return value


def _quantize(value: float) -> float:
    rounded = round(_finite(float(value), "summary value"), QUANTIZATION_DECIMALS)
    return 0.0 if rounded == 0.0 else rounded


def _quantize_optional(value: float | None) -> float | None:
    return None if value is None else _quantize(value)


def _quantized_difference(left: float, right: float) -> float:
    return _quantize(_quantize(left) - _quantize(right))


@dataclass(frozen=True, slots=True)
class DiscordanceFitConfiguration:
    """Locked numerical and support gates for one development fit."""

    fold_count: int = FOLD_COUNT
    minimum_train_complete: int = DEFAULT_MINIMUM_TRAIN_COMPLETE
    minimum_test_complete: int = DEFAULT_MINIMUM_TEST_COMPLETE
    minimum_valid_folds: int = DEFAULT_MINIMUM_VALID_FOLDS
    minimum_oof: int = DEFAULT_MINIMUM_OOF
    bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES
    minimum_bootstrap_success_fraction: float = DEFAULT_MINIMUM_BOOTSTRAP_SUCCESS_FRACTION
    interval_level: float = INTERVAL_LEVEL
    quantization_decimals: int = QUANTIZATION_DECIMALS
    maximum_patient_groups: int = MAX_PATIENT_GROUPS

    def __post_init__(self) -> None:
        if _exact_int(self.fold_count, "fold_count") != FOLD_COUNT:
            raise ValueError("the discordance model requires exactly five folds")
        train = _exact_int(self.minimum_train_complete, "minimum_train_complete")
        test = _exact_int(self.minimum_test_complete, "minimum_test_complete")
        valid = _exact_int(self.minimum_valid_folds, "minimum_valid_folds")
        oof = _exact_int(self.minimum_oof, "minimum_oof")
        replicates = _exact_int(self.bootstrap_replicates, "bootstrap_replicates")
        decimals = _exact_int(self.quantization_decimals, "quantization_decimals")
        maximum = _exact_int(self.maximum_patient_groups, "maximum_patient_groups")
        if train < 3 or test < 3:
            raise ValueError("train and test complete-case minima must each be at least three")
        if not 1 <= valid <= FOLD_COUNT:
            raise ValueError("minimum_valid_folds must be between one and five")
        if oof < 3 or oof > maximum:
            raise ValueError("minimum_oof is outside the patient-group bound")
        if not 16 <= replicates <= MAX_BOOTSTRAP_REPLICATES:
            raise ValueError("bootstrap_replicates must be between 16 and 256")
        success = _finite(
            self.minimum_bootstrap_success_fraction,
            "minimum_bootstrap_success_fraction",
        )
        if not 0.5 < success <= 1.0:
            raise ValueError("minimum bootstrap success fraction must be in (0.5, 1]")
        if _finite(self.interval_level, "interval_level") != INTERVAL_LEVEL:
            raise ValueError("the development profile requires a 90% interval")
        if decimals != QUANTIZATION_DECIMALS:
            raise ValueError("the development profile requires eight-decimal quantization")
        if maximum < oof or maximum > MAX_PATIENT_GROUPS:
            raise ValueError("maximum_patient_groups is outside the locked bound")


@dataclass(frozen=True, slots=True)
class MetricSummary:
    """Quantized held-out metrics evaluated on one common OOF patient set."""

    patient_groups: int
    spearman: float | None
    r2_vs_fold_train_median: float
    mae: float
    residual_mad: float

    def __post_init__(self) -> None:
        if _exact_int(self.patient_groups, "patient_groups") < 3:
            raise ValueError("metric summaries require at least three patient groups")
        if self.spearman is not None:
            spearman = _finite(self.spearman, "spearman")
            if not -1.0 <= spearman <= 1.0:
                raise ValueError("spearman must lie in [-1, 1]")
        _finite(self.r2_vs_fold_train_median, "r2_vs_fold_train_median")
        if _finite(self.mae, "mae") < 0.0:
            raise ValueError("mae cannot be negative")
        if _finite(self.residual_mad, "residual_mad") < 0.0:
            raise ValueError("residual_mad cannot be negative")


@dataclass(frozen=True, slots=True)
class FiniteSampleInterval:
    """A quantized, interpolation-free percentile interval."""

    point_estimate: float
    lower: float
    upper: float
    confidence_level: float
    replicates: int

    def __post_init__(self) -> None:
        point = _finite(self.point_estimate, "point_estimate")
        lower = _finite(self.lower, "lower")
        upper = _finite(self.upper, "upper")
        if lower > upper:
            raise ValueError("finite-sample interval bounds are reversed")
        if _finite(self.confidence_level, "confidence_level") != INTERVAL_LEVEL:
            raise ValueError("only the locked 90% interval is supported")
        if _exact_int(self.replicates, "replicates") < 1:
            raise ValueError("an interval requires at least one successful replicate")
        # Bootstrap percentile intervals need not contain their point estimate.
        _ = point


@dataclass(frozen=True, slots=True)
class BootstrapSummary:
    """Deterministic stratified patient-bootstrap uncertainty."""

    seed: int
    replicates_requested: int
    replicates_successful: int
    full_model_r2: FiniteSampleInterval
    delta_r2_vs_rna_only: FiniteSampleInterval
    delta_r2_vs_cnv_only: FiniteSampleInterval
    full_model_mae: FiniteSampleInterval
    full_model_residual_mad: FiniteSampleInterval
    conditional_rna_slope: FiniteSampleInterval

    def __post_init__(self) -> None:
        seed = _exact_int(self.seed, "seed")
        requested = _exact_int(self.replicates_requested, "replicates_requested")
        successful = _exact_int(self.replicates_successful, "replicates_successful")
        if not 0 <= seed < 2**64:
            raise ValueError("bootstrap seed must be an unsigned 64-bit integer")
        if not 1 <= successful <= requested <= MAX_BOOTSTRAP_REPLICATES:
            raise ValueError("bootstrap counts must satisfy successful <= requested")
        intervals = (
            self.full_model_r2,
            self.delta_r2_vs_rna_only,
            self.delta_r2_vs_cnv_only,
            self.full_model_mae,
            self.full_model_residual_mad,
            self.conditional_rna_slope,
        )
        if any(type(interval) is not FiniteSampleInterval for interval in intervals):
            raise TypeError("bootstrap intervals must be exact FiniteSampleInterval values")
        if any(interval.replicates != successful for interval in intervals):
            raise ValueError("every bootstrap interval must use every successful replicate")


@dataclass(frozen=True, slots=True)
class FoldFitTrace:
    """Aggregate convergence receipt for one held-out patient fold."""

    fold: int
    training_complete: int
    held_out_complete: int
    full_iterations: int | None
    rna_only_iterations: int | None
    cnv_only_iterations: int | None
    full_converged: bool
    rna_only_converged: bool
    cnv_only_converged: bool
    conditional_rna_slope: float | None
    valid: bool
    failure_reason: str | None

    def __post_init__(self) -> None:
        fold = _exact_int(self.fold, "fold")
        if not 0 <= fold < FOLD_COUNT:
            raise ValueError("fold trace index is outside zero through four")
        if _exact_int(self.training_complete, "training_complete") < 0:
            raise ValueError("training_complete cannot be negative")
        if _exact_int(self.held_out_complete, "held_out_complete") < 0:
            raise ValueError("held_out_complete cannot be negative")
        for name, value in (
            ("full_iterations", self.full_iterations),
            ("rna_only_iterations", self.rna_only_iterations),
            ("cnv_only_iterations", self.cnv_only_iterations),
        ):
            if value is not None and _exact_int(value, name) < 1:
                raise ValueError(f"{name} must be positive when present")
        for name, value in (
            ("full_converged", self.full_converged),
            ("rna_only_converged", self.rna_only_converged),
            ("cnv_only_converged", self.cnv_only_converged),
            ("valid", self.valid),
        ):
            _exact_bool(value, name)
        if self.failure_reason is not None and type(self.failure_reason) is not str:
            raise TypeError("failure_reason must be an exact string when present")
        if self.conditional_rna_slope is not None:
            _finite(self.conditional_rna_slope, "conditional_rna_slope")
        converged = self.full_converged and self.rna_only_converged and self.cnv_only_converged
        if self.valid:
            if (
                not converged
                or self.conditional_rna_slope is None
                or self.failure_reason is not None
            ):
                raise ValueError("valid fold traces require three converged fits and a slope")
        elif self.failure_reason is None:
            raise ValueError("invalid fold traces require a failure reason")


@dataclass(frozen=True, slots=True)
class DiscordanceAggregateSummary:
    """De-identified, quantized aggregate candidate for a future artifact."""

    total_patient_groups: int
    complete_patient_groups: int
    oof_patient_groups: int
    valid_folds: int
    full_model: MetricSummary
    rna_only: MetricSummary
    cnv_only: MetricSummary
    training_median: MetricSummary
    delta_r2_vs_rna_only: float
    delta_r2_vs_cnv_only: float
    conditional_rna_slope_median: float
    conditional_rna_slope_mad: float
    conditional_rna_slope_sign_stability: float
    bootstrap: BootstrapSummary

    def __post_init__(self) -> None:
        if type(self.full_model) is not MetricSummary:
            raise TypeError("full_model must be an exact MetricSummary")
        if type(self.rna_only) is not MetricSummary:
            raise TypeError("rna_only must be an exact MetricSummary")
        if type(self.cnv_only) is not MetricSummary:
            raise TypeError("cnv_only must be an exact MetricSummary")
        if type(self.training_median) is not MetricSummary:
            raise TypeError("training_median must be an exact MetricSummary")
        if type(self.bootstrap) is not BootstrapSummary:
            raise TypeError("bootstrap must be an exact BootstrapSummary")
        total = _exact_int(self.total_patient_groups, "total_patient_groups")
        complete = _exact_int(self.complete_patient_groups, "complete_patient_groups")
        oof = _exact_int(self.oof_patient_groups, "oof_patient_groups")
        valid_folds = _exact_int(self.valid_folds, "valid_folds")
        if not 3 <= oof <= complete <= total <= MAX_PATIENT_GROUPS:
            raise ValueError("patient-group counts do not reconcile")
        if not 1 <= valid_folds <= FOLD_COUNT:
            raise ValueError("valid_folds is outside one through five")
        metric_counts = {
            self.full_model.patient_groups,
            self.rna_only.patient_groups,
            self.cnv_only.patient_groups,
            self.training_median.patient_groups,
        }
        if metric_counts != {oof}:
            raise ValueError("all comparator metrics must use the same OOF patient set")
        _finite(self.delta_r2_vs_rna_only, "delta_r2_vs_rna_only")
        _finite(self.delta_r2_vs_cnv_only, "delta_r2_vs_cnv_only")
        _finite(self.conditional_rna_slope_median, "conditional_rna_slope_median")
        if _finite(self.conditional_rna_slope_mad, "conditional_rna_slope_mad") < 0.0:
            raise ValueError("conditional_rna_slope_mad cannot be negative")
        stability = _finite(
            self.conditional_rna_slope_sign_stability,
            "conditional_rna_slope_sign_stability",
        )
        if not 0.0 <= stability <= 1.0:
            raise ValueError("conditional RNA slope sign stability must lie in [0, 1]")


def _immutable_float_array(value: FloatArray) -> FloatArray:
    contiguous = np.ascontiguousarray(value, dtype=np.float64)
    # ``bytes`` owns the storage, so callers cannot flip WRITEABLE back to true.
    return np.frombuffer(contiguous.tobytes(order="C"), dtype=np.float64)


def _validate_transient_array(value: object, expected_length: int, field_name: str) -> None:
    if type(value) is not np.ndarray:
        raise TypeError(f"{field_name} must be an exact ndarray")
    array = value
    if array.dtype != np.dtype(np.float64) or array.ndim != 1 or len(array) != expected_length:
        raise ValueError(f"{field_name} must be an aligned one-dimensional float64 array")
    if array.flags.writeable or type(getattr(array, "base", None)) is not bytes:
        raise ValueError(f"{field_name} must use immutable byte-backed storage")
    if bool(np.any(np.isinf(array))):
        raise ValueError(f"{field_name} cannot contain infinities")


@dataclass(frozen=True, slots=True)
class TransientOofPredictions:
    """Exact development-only OOF arrays that must never cross a service boundary."""

    observed_protein: FloatArray = field(repr=False)
    full_model: FloatArray = field(repr=False)
    rna_only: FloatArray = field(repr=False)
    cnv_only: FloatArray = field(repr=False)
    training_median: FloatArray = field(repr=False)
    full_model_residual: FloatArray = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.observed_protein) is not np.ndarray or self.observed_protein.ndim != 1:
            raise TypeError("observed_protein must be an exact one-dimensional ndarray")
        expected_length = len(self.observed_protein)
        for name in (
            "observed_protein",
            "full_model",
            "rna_only",
            "cnv_only",
            "training_median",
            "full_model_residual",
        ):
            _validate_transient_array(getattr(self, name), expected_length, name)
        arrays = (
            self.observed_protein,
            self.full_model,
            self.rna_only,
            self.cnv_only,
            self.training_median,
            self.full_model_residual,
        )
        masks = tuple(np.isfinite(item) for item in arrays)
        if any(not np.array_equal(masks[0], mask) for mask in masks[1:]):
            raise ValueError("all transient OOF arrays must have one exact support mask")
        residual = self.observed_protein[masks[0]] - self.full_model[masks[0]]
        if not np.array_equal(residual, self.full_model_residual[masks[0]]):
            raise ValueError("full_model_residual does not exactly match observed minus predicted")

    @property
    def patient_groups(self) -> int:
        """Return the total aligned patient-group count without exposing values."""

        return len(self.observed_protein)

    @property
    def oof_patient_groups(self) -> int:
        """Return the count with exact OOF support."""

        return int(np.isfinite(self.observed_protein).sum())

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient OOF arrays cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient OOF arrays cannot be serialized")


@dataclass(frozen=True, slots=True)
class TranscriptProteinDiscordanceDevelopmentFit:
    """One accepted in-memory fit plus its non-serializable OOF evaluation state."""

    request_digest: str
    configuration: DiscordanceFitConfiguration
    summary: DiscordanceAggregateSummary
    fold_trace: tuple[FoldFitTrace, ...]
    transient_oof: TransientOofPredictions = field(repr=False)

    def __post_init__(self) -> None:
        _validate_request_digest(self.request_digest)
        if type(self.configuration) is not DiscordanceFitConfiguration:
            raise TypeError("configuration must be an exact DiscordanceFitConfiguration")
        if type(self.summary) is not DiscordanceAggregateSummary:
            raise TypeError("summary must be an exact DiscordanceAggregateSummary")
        if type(self.fold_trace) is not tuple or any(
            type(item) is not FoldFitTrace for item in self.fold_trace
        ):
            raise TypeError("fold_trace must contain only exact FoldFitTrace values")
        if type(self.transient_oof) is not TransientOofPredictions:
            raise TypeError("transient_oof must be an exact TransientOofPredictions")
        if len(self.fold_trace) != FOLD_COUNT:
            raise ValueError("development fit requires one trace per fold")
        if tuple(item.fold for item in self.fold_trace) != tuple(range(FOLD_COUNT)):
            raise ValueError("fold traces must be sorted and complete")
        if sum(item.valid for item in self.fold_trace) != self.summary.valid_folds:
            raise ValueError("fold trace and aggregate valid-fold counts differ")
        if self.transient_oof.patient_groups != self.summary.total_patient_groups:
            raise ValueError("transient and aggregate total patient counts differ")
        if self.transient_oof.oof_patient_groups != self.summary.oof_patient_groups:
            raise ValueError("transient and aggregate OOF patient counts differ")

    def __getstate__(self) -> NoReturn:
        raise TypeError("development fits with transient OOF arrays cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("development fits with transient OOF arrays cannot be serialized")


@dataclass(frozen=True, slots=True)
class _RawMetricSummary:
    patient_groups: int
    spearman: float | None
    r2: float
    mae: float
    residual_mad: float


@dataclass(frozen=True, slots=True)
class _CrossFit:
    observed: FloatArray
    full: FloatArray
    rna_only: FloatArray
    cnv_only: FloatArray
    null: FloatArray
    slopes: tuple[float, ...]
    trace: tuple[FoldFitTrace, ...]


@dataclass(frozen=True, slots=True)
class _PointSummary:
    total: int
    complete: int
    oof: int
    valid_folds: int
    full: _RawMetricSummary
    rna_only: _RawMetricSummary
    cnv_only: _RawMetricSummary
    null: _RawMetricSummary
    delta_rna: float
    delta_cnv: float
    slope_median: float
    slope_mad: float
    slope_stability: float


def _validate_request_digest(value: object) -> str:
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError("request_digest must be a canonical lowercase sha256 digest")
    return value


def _bootstrap_seed(request_digest: str) -> int:
    digest_bytes = bytes.fromhex(request_digest.removeprefix("sha256:"))
    material = hashlib.sha256(_BOOTSTRAP_CONTEXT + digest_bytes).digest()
    return int.from_bytes(material[:8], "big", signed=False)


def _validate_inputs(
    cnv: object,
    rna: object,
    protein: object,
    folds: object,
    configuration: DiscordanceFitConfiguration,
) -> tuple[FloatArray, FloatArray, FloatArray, FoldArray]:
    arrays: list[FloatArray] = []
    for name, value in (("cnv", cnv), ("rna", rna), ("protein", protein)):
        if type(value) is not np.ndarray:
            raise TypeError(f"{name} must be an exact NumPy ndarray")
        array = value
        if array.dtype not in (np.dtype(np.float32), np.dtype(np.float64)):
            raise TypeError(f"{name} must have float32 or float64 dtype")
        if array.ndim != 1:
            raise ValueError(f"{name} must be one-dimensional")
        if bool(np.any(np.isinf(array))):
            raise ValueError(f"{name} contains infinity; only NaN may represent missingness")
        arrays.append(np.array(array, dtype=np.float64, copy=True))
    if type(folds) is not np.ndarray:
        raise TypeError("folds must be an exact NumPy ndarray")
    fold_array = folds
    if fold_array.dtype != np.dtype(np.int8) or fold_array.ndim != 1:
        raise TypeError("folds must be a one-dimensional int8 ndarray")
    lengths = {len(item) for item in (*arrays, fold_array)}
    if len(lengths) != 1:
        raise ValueError("CNV, RNA, protein, and folds must be exactly aligned")
    sample_count = len(arrays[0])
    if sample_count < configuration.minimum_oof:
        raise ValueError("the aligned cohort is smaller than the minimum OOF gate")
    if sample_count > configuration.maximum_patient_groups:
        raise ValueError("the aligned cohort exceeds the patient-group bound")
    observed_folds = set(np.unique(fold_array).tolist())
    if observed_folds != set(range(FOLD_COUNT)):
        raise ValueError("folds must contain every integer zero through four and no others")
    return arrays[0], arrays[1], arrays[2], np.array(fold_array, dtype=np.int8, copy=True)


def _canonical_row_order(
    cnv: FloatArray,
    rna: FloatArray,
    protein: FloatArray,
    folds: FoldArray,
) -> IndexArray:
    """Order anonymous rows by fold and values for permutation-stable computation.

    Patient identifiers are deliberately unavailable to this model.  Jointly
    permuting the aligned anonymous rows must nevertheless leave every aggregate
    receipt unchanged.  Missing values share one canonical key; ties are safe
    because tied rows are numerically identical for every model input.
    """

    def value_key(numeric: float) -> tuple[int, float]:
        return (1, 0.0) if math.isnan(numeric) else (0, numeric)

    def row_key(
        index: int,
    ) -> tuple[
        int,
        tuple[int, float],
        tuple[int, float],
        tuple[int, float],
    ]:
        return (
            int(folds[index]),
            value_key(float(cnv[index])),
            value_key(float(rna[index])),
            value_key(float(protein[index])),
        )

    return np.asarray(
        sorted(range(len(folds)), key=row_key),
        dtype=np.int64,
    )


def _restore_input_order(values: FloatArray, order: IndexArray) -> FloatArray:
    restored = np.empty_like(values)
    restored[order] = values
    return restored


def _average_ranks(values: FloatArray) -> FloatArray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    left = 0
    while left < len(values):
        right = left + 1
        while right < len(values) and values[order[right]] == values[order[left]]:
            right += 1
        ranks[order[left:right]] = (left + right - 1) / 2.0 + 1.0
        left = right
    return ranks


def _spearman(left: FloatArray, right: FloatArray) -> float | None:
    if len(left) < 3:
        return None
    left_ranks = _average_ranks(left)
    right_ranks = _average_ranks(right)
    if float(np.std(left_ranks)) < _NUMERICAL_ZERO:
        return None
    if float(np.std(right_ranks)) < _NUMERICAL_ZERO:
        return None
    value = float(np.corrcoef(left_ranks, right_ranks)[0, 1])
    return value if math.isfinite(value) else None


def _scaled_mad(values: FloatArray) -> float:
    center = float(np.median(values))
    return float(_ROBUST_SCALE_FACTOR * np.median(np.abs(values - center)))


def _metrics(
    truth: FloatArray,
    prediction: FloatArray,
    null_prediction: FloatArray,
) -> _RawMetricSummary | None:
    valid = np.isfinite(truth) & np.isfinite(prediction) & np.isfinite(null_prediction)
    observed = truth[valid]
    predicted = prediction[valid]
    baseline = null_prediction[valid]
    if len(observed) < 3:
        return None
    null_sse = float(np.sum((observed - baseline) ** 2, dtype=np.float64))
    if not math.isfinite(null_sse) or null_sse <= _NUMERICAL_ZERO:
        return None
    residual = observed - predicted
    model_sse = float(np.sum(residual**2, dtype=np.float64))
    r2 = 1.0 - model_sse / null_sse
    mae = float(np.mean(np.abs(residual), dtype=np.float64))
    residual_mad = _scaled_mad(residual)
    if not all(math.isfinite(item) for item in (r2, mae, residual_mad)):
        return None
    return _RawMetricSummary(
        patient_groups=len(observed),
        spearman=_spearman(observed, predicted),
        r2=r2,
        mae=mae,
        residual_mad=residual_mad,
    )


def _raw_conditional_rna_slope(fit: RobustFit) -> float | None:
    if len(fit.beta) != 3 or len(fit.x_scale) != 2:
        return None
    denominator = float(fit.x_scale[0])
    if not math.isfinite(denominator) or denominator <= _NUMERICAL_ZERO:
        return None
    value = float(fit.y_scale * fit.beta[1] / denominator)
    return value if math.isfinite(value) else None


def _failed_trace(
    fold: int,
    training_complete: int,
    held_out_complete: int,
    reason: str,
    fits: tuple[RobustFit | None, RobustFit | None, RobustFit | None] = (None, None, None),
) -> FoldFitTrace:
    full, rna_only, cnv_only = fits
    return FoldFitTrace(
        fold=fold,
        training_complete=training_complete,
        held_out_complete=held_out_complete,
        full_iterations=None if full is None else full.iterations,
        rna_only_iterations=None if rna_only is None else rna_only.iterations,
        cnv_only_iterations=None if cnv_only is None else cnv_only.iterations,
        full_converged=full is not None and full.converged,
        rna_only_converged=rna_only is not None and rna_only.converged,
        cnv_only_converged=cnv_only is not None and cnv_only.converged,
        conditional_rna_slope=None,
        valid=False,
        failure_reason=reason,
    )


def _cross_fit(  # noqa: PLR0915
    cnv: FloatArray,
    rna: FloatArray,
    protein: FloatArray,
    folds: FoldArray,
    configuration: DiscordanceFitConfiguration,
) -> _CrossFit | None:
    count = len(protein)
    observed = np.full(count, np.nan, dtype=np.float64)
    full_prediction = np.full(count, np.nan, dtype=np.float64)
    rna_prediction = np.full(count, np.nan, dtype=np.float64)
    cnv_prediction = np.full(count, np.nan, dtype=np.float64)
    null_prediction = np.full(count, np.nan, dtype=np.float64)
    complete = np.isfinite(cnv) & np.isfinite(rna) & np.isfinite(protein)
    traces: list[FoldFitTrace] = []
    slopes: list[float] = []

    for fold in range(FOLD_COUNT):
        training = complete & (folds != fold)
        held_out = complete & (folds == fold)
        training_count = int(training.sum())
        held_out_count = int(held_out.sum())
        if training_count < configuration.minimum_train_complete:
            traces.append(
                _failed_trace(
                    fold,
                    training_count,
                    held_out_count,
                    "insufficient training complete cases",
                )
            )
            continue
        if held_out_count < configuration.minimum_test_complete:
            traces.append(
                _failed_trace(
                    fold,
                    training_count,
                    held_out_count,
                    "insufficient held-out complete cases",
                )
            )
            continue
        full_fit = fit_huber(
            np.column_stack((rna[training], cnv[training])),
            protein[training],
        )
        rna_fit = fit_huber(rna[training, None], protein[training])
        cnv_fit = fit_huber(cnv[training, None], protein[training])
        fits = (full_fit, rna_fit, cnv_fit)
        if any(item is None for item in fits):
            traces.append(
                _failed_trace(
                    fold,
                    training_count,
                    held_out_count,
                    "one or more fold models were numerically unidentified",
                    fits,
                )
            )
            continue
        if any(not item.converged for item in fits if item is not None):
            traces.append(
                _failed_trace(
                    fold,
                    training_count,
                    held_out_count,
                    "one or more fold models did not converge",
                    fits,
                )
            )
            continue
        if full_fit is None or rna_fit is None or cnv_fit is None:  # pragma: no cover
            raise AssertionError("validated fold fits unexpectedly disappeared")
        slope = _raw_conditional_rna_slope(full_fit)
        if slope is None:
            traces.append(
                _failed_trace(
                    fold,
                    training_count,
                    held_out_count,
                    "conditional RNA slope could not be recovered on the raw scale",
                    fits,
                )
            )
            continue
        full_values = full_fit.predict(np.column_stack((rna[held_out], cnv[held_out])))
        rna_values = rna_fit.predict(rna[held_out, None])
        cnv_values = cnv_fit.predict(cnv[held_out, None])
        predictions = (full_values, rna_values, cnv_values)
        if any(not bool(np.all(np.isfinite(item))) for item in predictions):
            traces.append(
                _failed_trace(
                    fold,
                    training_count,
                    held_out_count,
                    "one or more held-out predictions were non-finite",
                    fits,
                )
            )
            continue
        observed[held_out] = protein[held_out]
        full_prediction[held_out] = full_values
        rna_prediction[held_out] = rna_values
        cnv_prediction[held_out] = cnv_values
        null_prediction[held_out] = float(np.median(protein[training]))
        slopes.append(slope)
        traces.append(
            FoldFitTrace(
                fold=fold,
                training_complete=training_count,
                held_out_complete=held_out_count,
                full_iterations=full_fit.iterations,
                rna_only_iterations=rna_fit.iterations,
                cnv_only_iterations=cnv_fit.iterations,
                full_converged=True,
                rna_only_converged=True,
                cnv_only_converged=True,
                conditional_rna_slope=_quantize(slope),
                valid=True,
                failure_reason=None,
            )
        )

    if len(slopes) < configuration.minimum_valid_folds:
        return None
    if int(np.isfinite(observed).sum()) < configuration.minimum_oof:
        return None
    return _CrossFit(
        observed=observed,
        full=full_prediction,
        rna_only=rna_prediction,
        cnv_only=cnv_prediction,
        null=null_prediction,
        slopes=tuple(slopes),
        trace=tuple(traces),
    )


def _sign_stability(values: tuple[float, ...]) -> float:
    finite = tuple(value for value in values if math.isfinite(value) and abs(value) > _SLOPE_ZERO)
    if not finite:
        return 0.0
    median = float(np.median(finite))
    if abs(median) <= _SLOPE_ZERO:
        return 0.0
    expected = 1 if median > 0.0 else -1
    agreeing = sum((1 if value > 0.0 else -1) == expected for value in finite)
    return agreeing / len(finite)


def _point_summary(
    cross_fit: _CrossFit,
    *,
    total: int,
    complete: int,
) -> _PointSummary | None:
    full = _metrics(cross_fit.observed, cross_fit.full, cross_fit.null)
    rna_only = _metrics(cross_fit.observed, cross_fit.rna_only, cross_fit.null)
    cnv_only = _metrics(cross_fit.observed, cross_fit.cnv_only, cross_fit.null)
    null = _metrics(cross_fit.observed, cross_fit.null, cross_fit.null)
    if full is None or rna_only is None or cnv_only is None or null is None:
        return None
    counts = {
        full.patient_groups,
        rna_only.patient_groups,
        cnv_only.patient_groups,
        null.patient_groups,
    }
    if len(counts) != 1:
        return None
    slope_array = np.asarray(cross_fit.slopes, dtype=np.float64)
    slope_median = float(np.median(slope_array))
    slope_mad = _scaled_mad(slope_array)
    values = (
        full.r2,
        rna_only.r2,
        cnv_only.r2,
        slope_median,
        slope_mad,
    )
    if not all(math.isfinite(item) for item in values):
        return None
    return _PointSummary(
        total=total,
        complete=complete,
        oof=full.patient_groups,
        valid_folds=len(cross_fit.slopes),
        full=full,
        rna_only=rna_only,
        cnv_only=cnv_only,
        null=null,
        delta_rna=full.r2 - rna_only.r2,
        delta_cnv=full.r2 - cnv_only.r2,
        slope_median=slope_median,
        slope_mad=slope_mad,
        slope_stability=_sign_stability(cross_fit.slopes),
    )


def _stratified_patient_bootstrap_indices(
    folds: FoldArray,
    rng: np.random.Generator,
) -> IndexArray:
    draws: list[IndexArray] = []
    for fold in range(FOLD_COUNT):
        members = np.flatnonzero(folds == fold)
        selected = rng.choice(members, size=len(members), replace=True)
        draws.append(np.asarray(selected, dtype=np.int64))
    return np.concatenate(draws).astype(np.int64, copy=False)


def _finite_sample_interval(
    samples: list[float],
    point_estimate: float,
) -> FiniteSampleInterval:
    ordered = np.sort(np.asarray(samples, dtype=np.float64), kind="mergesort")
    count = len(ordered)
    if count < 1 or not bool(np.all(np.isfinite(ordered))):
        raise ValueError("finite-sample intervals require finite bootstrap values")
    # Conventional nearest-rank percentiles use ceil(B * p), without interpolation.
    lower_rank = max(1, math.ceil(count * 0.05))
    upper_rank = min(count, math.ceil(count * 0.95))
    return FiniteSampleInterval(
        point_estimate=_quantize(point_estimate),
        lower=_quantize(float(ordered[lower_rank - 1])),
        upper=_quantize(float(ordered[upper_rank - 1])),
        confidence_level=INTERVAL_LEVEL,
        replicates=count,
    )


def _bootstrap(  # noqa: PLR0917
    cnv: FloatArray,
    rna: FloatArray,
    protein: FloatArray,
    folds: FoldArray,
    point: _PointSummary,
    request_digest: str,
    configuration: DiscordanceFitConfiguration,
) -> BootstrapSummary | None:
    seed = _bootstrap_seed(request_digest)
    rng = np.random.default_rng(seed)
    full_r2: list[float] = []
    delta_rna: list[float] = []
    delta_cnv: list[float] = []
    full_mae: list[float] = []
    residual_mad: list[float] = []
    slopes: list[float] = []
    for _ in range(configuration.bootstrap_replicates):
        indices = _stratified_patient_bootstrap_indices(folds, rng)
        sampled_cnv = cnv[indices]
        sampled_rna = rna[indices]
        sampled_protein = protein[indices]
        sampled_folds = folds[indices]
        sampled_cross_fit = _cross_fit(
            sampled_cnv,
            sampled_rna,
            sampled_protein,
            sampled_folds,
            configuration,
        )
        if sampled_cross_fit is None:
            continue
        sampled_complete = int(
            (
                np.isfinite(sampled_cnv) & np.isfinite(sampled_rna) & np.isfinite(sampled_protein)
            ).sum()
        )
        sampled_point = _point_summary(
            sampled_cross_fit,
            total=len(indices),
            complete=sampled_complete,
        )
        if sampled_point is None:
            continue
        full_r2.append(sampled_point.full.r2)
        delta_rna.append(sampled_point.delta_rna)
        delta_cnv.append(sampled_point.delta_cnv)
        full_mae.append(sampled_point.full.mae)
        residual_mad.append(sampled_point.full.residual_mad)
        slopes.append(sampled_point.slope_median)
    successful = len(full_r2)
    required = math.ceil(
        configuration.bootstrap_replicates * configuration.minimum_bootstrap_success_fraction
    )
    tracks = (full_r2, delta_rna, delta_cnv, full_mae, residual_mad, slopes)
    if successful < required or any(len(track) != successful for track in tracks):
        return None
    return BootstrapSummary(
        seed=seed,
        replicates_requested=configuration.bootstrap_replicates,
        replicates_successful=successful,
        full_model_r2=_finite_sample_interval(full_r2, point.full.r2),
        delta_r2_vs_rna_only=_finite_sample_interval(
            delta_rna,
            _quantized_difference(point.full.r2, point.rna_only.r2),
        ),
        delta_r2_vs_cnv_only=_finite_sample_interval(
            delta_cnv,
            _quantized_difference(point.full.r2, point.cnv_only.r2),
        ),
        full_model_mae=_finite_sample_interval(full_mae, point.full.mae),
        full_model_residual_mad=_finite_sample_interval(
            residual_mad,
            point.full.residual_mad,
        ),
        conditional_rna_slope=_finite_sample_interval(slopes, point.slope_median),
    )


def _metric_document(value: _RawMetricSummary) -> MetricSummary:
    return MetricSummary(
        patient_groups=value.patient_groups,
        spearman=_quantize_optional(value.spearman),
        r2_vs_fold_train_median=_quantize(value.r2),
        mae=_quantize(value.mae),
        residual_mad=_quantize(value.residual_mad),
    )


def _aggregate_summary(
    point: _PointSummary,
    bootstrap: BootstrapSummary,
) -> DiscordanceAggregateSummary:
    full_model = _metric_document(point.full)
    rna_only = _metric_document(point.rna_only)
    cnv_only = _metric_document(point.cnv_only)
    return DiscordanceAggregateSummary(
        total_patient_groups=point.total,
        complete_patient_groups=point.complete,
        oof_patient_groups=point.oof,
        valid_folds=point.valid_folds,
        full_model=full_model,
        rna_only=rna_only,
        cnv_only=cnv_only,
        training_median=_metric_document(point.null),
        delta_r2_vs_rna_only=_quantized_difference(
            full_model.r2_vs_fold_train_median,
            rna_only.r2_vs_fold_train_median,
        ),
        delta_r2_vs_cnv_only=_quantized_difference(
            full_model.r2_vs_fold_train_median,
            cnv_only.r2_vs_fold_train_median,
        ),
        conditional_rna_slope_median=_quantize(point.slope_median),
        conditional_rna_slope_mad=_quantize(point.slope_mad),
        conditional_rna_slope_sign_stability=_quantize(point.slope_stability),
        bootstrap=bootstrap,
    )


def fit_transcript_protein_discordance_gene(
    cnv: InputFloatArray,
    rna: InputFloatArray,
    protein: InputFloatArray,
    folds: FoldArray,
    *,
    request_digest: str,
    configuration: DiscordanceFitConfiguration | None = None,
) -> TranscriptProteinDiscordanceDevelopmentFit | None:
    """Fit one gene with leakage-safe five-fold evaluation and patient bootstrap.

    Each row must represent one already resolved patient group.  ``NaN`` is the
    only missing-value marker; infinity is rejected.  Malformed arrays raise an
    exception.  Numerically unidentified, insufficiently observed, non-converged,
    or bootstrap-unstable genes return ``None`` and must be treated as abstained.

    ``request_digest`` seeds only bootstrap resampling.  The point fit and exact
    OOF predictions are independent of that digest.
    """

    resolved_configuration = configuration or DiscordanceFitConfiguration()
    if type(resolved_configuration) is not DiscordanceFitConfiguration:
        raise TypeError("configuration must be an exact DiscordanceFitConfiguration")
    digest = _validate_request_digest(request_digest)
    cnv_array, rna_array, protein_array, fold_array = _validate_inputs(
        cnv,
        rna,
        protein,
        folds,
        resolved_configuration,
    )
    complete_count = int(
        (np.isfinite(cnv_array) & np.isfinite(rna_array) & np.isfinite(protein_array)).sum()
    )
    if complete_count < resolved_configuration.minimum_oof:
        return None
    canonical_order = _canonical_row_order(cnv_array, rna_array, protein_array, fold_array)
    ordered_cnv = cnv_array[canonical_order]
    ordered_rna = rna_array[canonical_order]
    ordered_protein = protein_array[canonical_order]
    ordered_folds = fold_array[canonical_order]
    cross_fit = _cross_fit(
        ordered_cnv,
        ordered_rna,
        ordered_protein,
        ordered_folds,
        resolved_configuration,
    )
    if cross_fit is None:
        return None
    point = _point_summary(
        cross_fit,
        total=len(protein_array),
        complete=complete_count,
    )
    if point is None:
        return None
    bootstrap = _bootstrap(
        ordered_cnv,
        ordered_rna,
        ordered_protein,
        ordered_folds,
        point,
        digest,
        resolved_configuration,
    )
    if bootstrap is None:
        return None
    canonical_support = np.isfinite(cross_fit.observed)
    observed = _restore_input_order(
        np.where(canonical_support, cross_fit.observed, np.nan),
        canonical_order,
    )
    full = _restore_input_order(
        np.where(canonical_support, cross_fit.full, np.nan),
        canonical_order,
    )
    rna_only = _restore_input_order(
        np.where(canonical_support, cross_fit.rna_only, np.nan),
        canonical_order,
    )
    cnv_only = _restore_input_order(
        np.where(canonical_support, cross_fit.cnv_only, np.nan),
        canonical_order,
    )
    null = _restore_input_order(
        np.where(canonical_support, cross_fit.null, np.nan),
        canonical_order,
    )
    support = np.isfinite(observed)
    residual = np.where(support, observed - full, np.nan)
    transient = TransientOofPredictions(
        observed_protein=_immutable_float_array(observed),
        full_model=_immutable_float_array(full),
        rna_only=_immutable_float_array(rna_only),
        cnv_only=_immutable_float_array(cnv_only),
        training_median=_immutable_float_array(null),
        full_model_residual=_immutable_float_array(residual),
    )
    return TranscriptProteinDiscordanceDevelopmentFit(
        request_digest=digest,
        configuration=resolved_configuration,
        summary=_aggregate_summary(point, bootstrap),
        fold_trace=cross_fit.trace,
        transient_oof=transient,
    )


__all__ = [
    "DEFAULT_BOOTSTRAP_REPLICATES",
    "DiscordanceAggregateSummary",
    "DiscordanceFitConfiguration",
    "FiniteSampleInterval",
    "FoldFitTrace",
    "MetricSummary",
    "TranscriptProteinDiscordanceDevelopmentFit",
    "TransientOofPredictions",
    "fit_transcript_protein_discordance_gene",
]

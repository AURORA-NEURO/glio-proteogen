"""Aggregate diagnostics for local, exact-source discordance development fits.

This additive evaluator does not change the 1.0 estimator, artifact, or query
profile. It independently replays point fits through the public shared Huber
solver, including when the bootstrap fit abstains. No patient arrays leave this
module. Calibration and residual associations are descriptive held-out checks;
they do not provide hypothesis tests, causal effects, or calibrated intervals.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Final

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.cptac_gbm_cis_dosage.model import RobustFit, fit_huber

from .model import (
    FOLD_COUNT,
    MAX_PATIENT_GROUPS,
    DiscordanceFitConfiguration,
    TranscriptProteinDiscordanceDevelopmentFit,
)

CONDITION_NUMBER_CEILING: Final = 1_000_000.0
RESIDUAL_RNA_FRACTION_FLOOR: Final = 0.000001
MAX_ABSOLUTE_INPUT: Final = 1_000_000_000_000.0
_ZERO: Final = 1e-12
FloatArray = npt.NDArray[np.float64]
FoldArray = npt.NDArray[np.int8]


@dataclass(frozen=True, slots=True)
class MissingnessPattern:
    missing_cnv: bool
    missing_rna: bool
    missing_protein: bool
    count: int


@dataclass(frozen=True, slots=True)
class ConditionalDesignDiagnostic:
    rank: int
    columns: int
    condition_number: float | None
    residual_rna_fraction: float | None
    cnv_rna_correlation: float | None
    numerically_identified: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FoldInputEvaluation:
    fold: int
    training_complete: int
    held_out_complete: int
    point_fit_accepted: bool
    full_converged: bool | None
    rna_only_converged: bool | None
    cnv_only_converged: bool | None
    full_iterations: int | None
    rna_only_iterations: int | None
    cnv_only_iterations: int | None
    failure_reason: str | None
    conditional_design: ConditionalDesignDiagnostic | None


@dataclass(frozen=True, slots=True)
class OofReconstructionMetrics:
    observed_count: int
    mae: float
    rmse: float
    r2_vs_fold_train_median: float | None
    pearson: float | None
    residual_mad: float
    calibration_intercept: float | None
    calibration_slope: float | None
    residual_rna_correlation: float | None
    residual_cnv_correlation: float | None


@dataclass(frozen=True, slots=True)
class GeneInputEvaluation:
    total_count: int
    complete_count: int
    missing_cnv_count: int
    missing_rna_count: int
    missing_protein_count: int
    missingness_patterns: tuple[MissingnessPattern, ...]
    folds: tuple[FoldInputEvaluation, ...]
    valid_point_fold_count: int
    common_oof_count: int
    point_fit_accepted: bool
    point_failure_reasons: tuple[str, ...]
    conditional_design_unidentified: bool
    conditional_effect_reportable: bool
    bootstrap_fit_supplied: bool
    supplied_fit_point_agreement: bool | None
    full_model: OofReconstructionMetrics | None
    rna_only: OofReconstructionMetrics | None
    cnv_only: OofReconstructionMetrics | None
    training_median: OofReconstructionMetrics | None
    delta_r2_vs_rna_only: float | None
    delta_r2_vs_cnv_only: float | None
    limitations: tuple[str, ...]


def _inputs(
    cnv: object, rna: object, protein: object, folds: object
) -> tuple[FloatArray, FloatArray, FloatArray, FoldArray]:
    arrays = []
    for name, value in (("cnv", cnv), ("rna", rna), ("protein", protein)):
        if type(value) is not np.ndarray or value.dtype not in (
            np.dtype(np.float32),
            np.dtype(np.float64),
        ):
            raise TypeError(f"{name} must be an exact float32 or float64 ndarray")
        if value.ndim != 1:
            raise ValueError(f"{name} must be one-dimensional")
        if bool(np.any(np.isinf(value))) or bool(
            np.any(np.abs(value[np.isfinite(value)]) > MAX_ABSOLUTE_INPUT)
        ):
            raise ValueError(f"{name} contains an infinite or out-of-bound value")
        arrays.append(np.array(value, dtype=np.float64, copy=True))
    if type(folds) is not np.ndarray or folds.dtype != np.dtype(np.int8) or folds.ndim != 1:
        raise TypeError("folds must be an exact one-dimensional int8 ndarray")
    if len({len(value) for value in (*arrays, folds)}) != 1:
        raise ValueError("CNV, RNA, protein, and folds must be exactly aligned")
    if not FOLD_COUNT <= len(folds) <= MAX_PATIENT_GROUPS:
        raise ValueError("diagnostic cohort size is outside the supported bound")
    if set(np.unique(folds).tolist()) != set(range(FOLD_COUNT)):
        raise ValueError("folds must contain exactly zero through four")
    return arrays[0], arrays[1], arrays[2], np.array(folds, dtype=np.int8, copy=True)


def _canonical_order(
    cnv: FloatArray, rna: FloatArray, protein: FloatArray, folds: FoldArray
) -> npt.NDArray[np.int64]:
    def numeric_key(value: float) -> tuple[int, float]:
        return (1, 0.0) if np.isnan(value) else (0, value)

    return np.asarray(
        sorted(
            range(len(folds)),
            key=lambda index: (
                int(folds[index]),
                numeric_key(float(cnv[index])),
                numeric_key(float(rna[index])),
                numeric_key(float(protein[index])),
            ),
        ),
        dtype=np.int64,
    )


def _correlation(left: FloatArray, right: FloatArray) -> float | None:
    if len(left) < 3:
        return None
    centered_left, centered_right = left - np.mean(left), right - np.mean(right)
    denominator = sqrt(
        float(np.dot(centered_left, centered_left)) * float(np.dot(centered_right, centered_right))
    )
    if denominator <= _ZERO:
        return None
    return max(-1.0, min(1.0, float(np.dot(centered_left, centered_right)) / denominator))


def _design(cnv: FloatArray, rna: FloatArray) -> ConditionalDesignDiagnostic | None:
    if len(cnv) < 3:
        return None
    centered = np.column_stack((rna - np.mean(rna), cnv - np.mean(cnv)))
    scales = np.std(centered, axis=0, ddof=1)
    standardized = np.zeros_like(centered)
    for column in range(2):
        if scales[column] > _ZERO:
            standardized[:, column] = centered[:, column] / scales[column]
    design = np.column_stack((np.ones(len(cnv)), standardized))
    singular = np.linalg.svd(design, compute_uv=False)
    tolerance = np.finfo(np.float64).eps * max(design.shape) * float(singular[0])
    rank = int(np.sum(singular > tolerance))
    condition = float(singular[0] / singular[-1]) if rank == 3 else None
    residual_fraction = None
    rna_ss = float(np.dot(standardized[:, 0], standardized[:, 0]))
    if rna_ss > _ZERO:
        nuisance = np.column_stack((np.ones(len(cnv)), standardized[:, 1]))
        coefficient = np.linalg.lstsq(nuisance, standardized[:, 0], rcond=None)[0]
        residual = standardized[:, 0] - nuisance @ coefficient
        residual_fraction = min(1.0, max(0.0, float(np.dot(residual, residual)) / rna_ss))
    reasons = []
    if rank < 3:
        reasons.append("standardized intercept/RNA/CNV design is rank deficient")
    if condition is not None and condition > CONDITION_NUMBER_CEILING:
        reasons.append("standardized design condition number exceeds 1000000")
    if residual_fraction is None:
        reasons.append("RNA has no estimable training variance")
    elif residual_fraction < RESIDUAL_RNA_FRACTION_FLOOR:
        reasons.append(
            "less than one millionth of RNA variance remains after linear CNV adjustment"
        )
    return ConditionalDesignDiagnostic(
        rank=rank,
        columns=3,
        condition_number=condition,
        residual_rna_fraction=residual_fraction,
        cnv_rna_correlation=_correlation(cnv, rna),
        numerically_identified=not reasons,
        reasons=tuple(reasons),
    )


def _fold(
    cnv: FloatArray,
    rna: FloatArray,
    protein: FloatArray,
    folds: FoldArray,
    complete: npt.NDArray[np.bool_],
    *,
    fold: int,
    configuration: DiscordanceFitConfiguration,
) -> tuple[FoldInputEvaluation, tuple[FloatArray, ...] | None]:
    training = complete & (folds != fold)
    held_out = complete & (folds == fold)
    training_count, held_out_count = int(training.sum()), int(held_out.sum())
    diagnostic = _design(cnv[training], rna[training])
    fits: tuple[RobustFit | None, ...] = (None, None, None)
    predictions = None
    failure = None
    if training_count < configuration.minimum_train_complete:
        failure = "insufficient training complete cases"
    elif held_out_count < configuration.minimum_test_complete:
        failure = "insufficient held-out complete cases"
    else:
        fits = (
            fit_huber(np.column_stack((rna[training], cnv[training])), protein[training]),
            fit_huber(rna[training, None], protein[training]),
            fit_huber(cnv[training, None], protein[training]),
        )
        if any(fit is None for fit in fits):
            failure = "one or more fold models were numerically unidentified"
        elif any(not fit.converged for fit in fits if fit is not None):
            failure = "one or more fold models did not converge"
        else:
            full, rna_only, cnv_only = fits
            if full is None or rna_only is None or cnv_only is None:  # pragma: no cover
                raise AssertionError("validated fits unexpectedly disappeared")
            slope = float(full.y_scale * full.beta[1] / full.x_scale[0])
            if not isfinite(slope):
                failure = "conditional RNA slope could not be recovered on the raw scale"
            else:
                predictions = (
                    full.predict(np.column_stack((rna[held_out], cnv[held_out]))),
                    rna_only.predict(rna[held_out, None]),
                    cnv_only.predict(cnv[held_out, None]),
                    np.full(held_out_count, np.median(protein[training]), dtype=np.float64),
                )
                if any(not bool(np.all(np.isfinite(values))) for values in predictions):
                    failure = "one or more held-out predictions were non-finite"
                    predictions = None
    full, rna_only, cnv_only = fits
    return FoldInputEvaluation(
        fold=fold,
        training_complete=training_count,
        held_out_complete=held_out_count,
        point_fit_accepted=failure is None,
        full_converged=None if full is None else full.converged,
        rna_only_converged=None if rna_only is None else rna_only.converged,
        cnv_only_converged=None if cnv_only is None else cnv_only.converged,
        full_iterations=None if full is None else full.iterations,
        rna_only_iterations=None if rna_only is None else rna_only.iterations,
        cnv_only_iterations=None if cnv_only is None else cnv_only.iterations,
        failure_reason=failure,
        conditional_design=diagnostic,
    ), predictions


def _metrics(
    truth: FloatArray, predicted: FloatArray, baseline: FloatArray, rna: FloatArray, cnv: FloatArray
) -> OofReconstructionMetrics | None:
    if len(truth) < 3:
        return None
    residual = truth - predicted
    null_ss = float(np.dot(truth - baseline, truth - baseline))
    error_ss = float(np.dot(residual, residual))
    prediction_center = predicted - np.mean(predicted)
    prediction_ss = float(np.dot(prediction_center, prediction_center))
    slope = (
        float(np.dot(prediction_center, truth - np.mean(truth))) / prediction_ss
        if prediction_ss > _ZERO
        else None
    )
    intercept = float(np.mean(truth) - slope * np.mean(predicted)) if slope is not None else None
    return OofReconstructionMetrics(
        observed_count=len(truth),
        mae=float(np.mean(np.abs(residual))),
        rmse=sqrt(error_ss / len(truth)),
        r2_vs_fold_train_median=1.0 - error_ss / null_ss if null_ss > _ZERO else None,
        pearson=_correlation(truth, predicted),
        residual_mad=1.4826 * float(np.median(np.abs(residual - np.median(residual)))),
        calibration_intercept=intercept,
        calibration_slope=slope,
        residual_rna_correlation=_correlation(residual, rna),
        residual_cnv_correlation=_correlation(residual, cnv),
    )


def evaluate_gene_inputs(
    cnv: object,
    rna: object,
    protein: object,
    folds: object,
    *,
    fit: TranscriptProteinDiscordanceDevelopmentFit | None = None,
) -> GeneInputEvaluation:
    """Return only aggregate missingness, identification, and OOF diagnostics.

    ``fit`` is the existing accepted bootstrap fit, if any. Point fits are
    recomputed even when it is absent, exposing the support/convergence failure
    that an absent 1.0 artifact entry otherwise cannot explain. The diagnostic
    design flag never rewrites a 1.0 result or implies biological identifiability.
    """

    if fit is not None and type(fit) is not TranscriptProteinDiscordanceDevelopmentFit:
        raise TypeError("fit must be an exact development fit or None")
    cnv_values, rna_values, protein_values, fold_values = _inputs(cnv, rna, protein, folds)
    order = _canonical_order(cnv_values, rna_values, protein_values, fold_values)
    cnv_values, rna_values, protein_values, fold_values = (
        cnv_values[order],
        rna_values[order],
        protein_values[order],
        fold_values[order],
    )
    configuration = fit.configuration if fit is not None else DiscordanceFitConfiguration()
    missing = np.column_stack(
        (np.isnan(cnv_values), np.isnan(rna_values), np.isnan(protein_values))
    )
    complete = ~np.any(missing, axis=1)
    patterns = tuple(
        MissingnessPattern(
            missing_cnv=bool(index & 4),
            missing_rna=bool(index & 2),
            missing_protein=bool(index & 1),
            count=int(
                np.sum(
                    np.all(
                        missing == np.asarray((bool(index & 4), bool(index & 2), bool(index & 1))),
                        axis=1,
                    )
                )
            ),
        )
        for index in range(8)
    )
    predictions = tuple(np.full(len(protein_values), np.nan, dtype=np.float64) for _ in range(4))
    traces = []
    for fold in range(FOLD_COUNT):
        trace, values = _fold(
            cnv_values,
            rna_values,
            protein_values,
            fold_values,
            complete,
            fold=fold,
            configuration=configuration,
        )
        traces.append(trace)
        if values is not None:
            held_out = complete & (fold_values == fold)
            for target, source in zip(predictions, values, strict=True):
                target[held_out] = source
    support = complete & np.all(
        np.column_stack(tuple(np.isfinite(value) for value in predictions)), axis=1
    )
    oof_count = int(support.sum())
    metrics = tuple(
        _metrics(
            protein_values[support],
            prediction[support],
            predictions[3][support],
            rna_values[support],
            cnv_values[support],
        )
        for prediction in predictions
    )
    point_failures = []
    valid_folds = sum(trace.point_fit_accepted for trace in traces)
    if valid_folds < configuration.minimum_valid_folds:
        point_failures.append("fewer than four valid point-fit folds")
    if oof_count < configuration.minimum_oof:
        point_failures.append("fewer than sixty common out-of-fold observations")
    if any(metric is None or metric.r2_vs_fold_train_median is None for metric in metrics):
        point_failures.append("common-support reconstruction metrics are not estimable")
    eligible_designs = tuple(
        trace.conditional_design
        for trace in traces
        if trace.training_complete >= configuration.minimum_train_complete
    )
    design_unidentified = not eligible_designs or any(
        design is None or not design.numerically_identified for design in eligible_designs
    )
    agreement = None
    if fit is not None:
        actual = fit.transient_oof
        if actual.patient_groups != len(protein_values):
            raise ValueError("supplied development fit does not match the input cohort size")
        expected = (
            actual.full_model[order],
            actual.rna_only[order],
            actual.cnv_only[order],
            actual.training_median[order],
        )
        agreement = all(
            np.array_equal(value, expected_value, equal_nan=True)
            for value, expected_value in zip(predictions, expected, strict=True)
        )
        agreement = agreement and np.array_equal(
            np.where(support, protein_values, np.nan),
            actual.observed_protein[order],
            equal_nan=True,
        )
    full, rna_only, cnv_only, baseline = metrics
    return GeneInputEvaluation(
        total_count=len(protein_values),
        complete_count=int(complete.sum()),
        missing_cnv_count=int(missing[:, 0].sum()),
        missing_rna_count=int(missing[:, 1].sum()),
        missing_protein_count=int(missing[:, 2].sum()),
        missingness_patterns=patterns,
        folds=tuple(traces),
        valid_point_fold_count=valid_folds,
        common_oof_count=oof_count,
        point_fit_accepted=not point_failures,
        point_failure_reasons=tuple(point_failures),
        conditional_design_unidentified=design_unidentified,
        conditional_effect_reportable=fit is not None
        and agreement is True
        and not design_unidentified,
        bootstrap_fit_supplied=fit is not None,
        supplied_fit_point_agreement=agreement,
        full_model=full,
        rna_only=rna_only,
        cnv_only=cnv_only,
        training_median=baseline,
        delta_r2_vs_rna_only=full.r2_vs_fold_train_median - rna_only.r2_vs_fold_train_median
        if full is not None
        and rna_only is not None
        and full.r2_vs_fold_train_median is not None
        and rna_only.r2_vs_fold_train_median is not None
        else None,
        delta_r2_vs_cnv_only=full.r2_vs_fold_train_median - cnv_only.r2_vs_fold_train_median
        if full is not None
        and cnv_only is not None
        and full.r2_vs_fold_train_median is not None
        and cnv_only.r2_vs_fold_train_median is not None
        else None,
        limitations=(
            "These are source-cohort descriptive diagnostics, not causal identifiability, p-values, or external validation.",
            "Rank and conditioning use training-only standardized intercept/RNA/CNV designs; thresholds are conservative numerical policy, not biological cutoffs.",
            "OOF calibration is a descriptive regression of held-out observed protein on held-out predictions, not a correction applied to the model.",
            "Complete-case evaluation does not correct informative missingness, and upstream whole-cohort source preprocessing is not re-fitted inside folds.",
            "No patient measurements, identifiers, fold memberships, predictions, or residual arrays are present in this aggregate diagnostic document.",
        ),
    )


__all__ = [
    "CONDITION_NUMBER_CEILING",
    "MAX_ABSOLUTE_INPUT",
    "RESIDUAL_RNA_FRACTION_FLOOR",
    "ConditionalDesignDiagnostic",
    "FoldInputEvaluation",
    "GeneInputEvaluation",
    "MissingnessPattern",
    "OofReconstructionMetrics",
    "evaluate_gene_inputs",
]

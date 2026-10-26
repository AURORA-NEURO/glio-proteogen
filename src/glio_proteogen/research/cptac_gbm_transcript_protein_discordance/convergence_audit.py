"""Matched-support numerical audit of four prespecified Huber iteration caps.

The public audit contains aggregate dataclasses only. Its development-only point
refitter exposes immutable, non-pickleable transient arrays to the separately
versioned continuation evaluator; those arrays never enter an audit receipt.
Neither interface changes the legacy estimator or its scientific claim ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite, sqrt
from typing import TYPE_CHECKING, NoReturn, SupportsIndex

import numpy as np
import numpy.typing as npt

from .convergence import ALLOWED_ITERATION_BUDGETS, fit_huber_with_budget
from .evaluation import MAX_ABSOLUTE_INPUT, evaluate_gene_inputs
from .model import (
    DEFAULT_MINIMUM_OOF,
    DEFAULT_MINIMUM_TEST_COMPLETE,
    DEFAULT_MINIMUM_TRAIN_COMPLETE,
    DEFAULT_MINIMUM_VALID_FOLDS,
    FOLD_COUNT,
    MAX_PATIENT_GROUPS,
    FoldFitTrace,
)

if TYPE_CHECKING:
    from glio_proteogen.research.cptac_gbm_cis_dosage.model import RobustFit

FloatArray = npt.NDArray[np.float64]
FoldArray = npt.NDArray[np.int8]


@dataclass(frozen=True, slots=True)
class BudgetPointRefit:
    """Development-only OOF values; never serialize into a research artifact."""

    max_iterations: int
    complete_count: int
    valid_folds: int
    oof_count: int
    accepted: bool
    raw_slopes: tuple[float, ...]
    fold_trace: tuple[FoldFitTrace, ...]
    observed: FloatArray = field(repr=False)
    predictions: tuple[FloatArray, ...] = field(repr=False)

    def __getstate__(self) -> NoReturn:
        raise TypeError("transient convergence point arrays cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("transient convergence point arrays cannot be serialized")


@dataclass(frozen=True, slots=True)
class MatchedReconstruction:
    observed_count: int
    mae: float
    rmse: float
    r2_vs_fold_train_median: float | None


@dataclass(frozen=True, slots=True)
class BudgetConvergenceAudit:
    max_iterations: int
    accepted_fold_count: int
    accepted_oof_count: int
    full_converged_fold_count: int
    rna_only_converged_fold_count: int
    cnv_only_converged_fold_count: int
    full_iteration_cap_exhausted_count: int
    rna_only_iteration_cap_exhausted_count: int
    cnv_only_iteration_cap_exhausted_count: int
    fold_trace: tuple[FoldFitTrace, ...]
    common_oof_count: int
    full_model: MatchedReconstruction | None
    rna_only: MatchedReconstruction | None
    cnv_only: MatchedReconstruction | None
    training_median: MatchedReconstruction | None


@dataclass(frozen=True, slots=True)
class ConvergenceBudgetEvaluation:
    total_count: int
    complete_count: int
    compared_budgets: tuple[int, ...]
    common_accepted_folds: tuple[int, ...]
    common_oof_count: int
    minimum_common_oof: int
    minimum_common_valid_folds: int
    comparison_status: str
    legacy_30_point_fit_accepted: bool
    legacy_30_fold_replay_agreement: bool
    budgets: tuple[BudgetConvergenceAudit, ...]
    promotes_legacy_artifact: bool
    provides_new_bootstrap_evidence: bool
    limitations: tuple[str, ...]


def _arrays(
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
        raise ValueError("convergence cohort size is outside the supported bound")
    if set(np.unique(folds).tolist()) != set(range(FOLD_COUNT)):
        raise ValueError("folds must contain exactly zero through four")
    return arrays[0], arrays[1], arrays[2], np.array(folds, dtype=np.int8, copy=True)


def _immutable(values: FloatArray) -> FloatArray:
    return np.frombuffer(np.ascontiguousarray(values).tobytes(), dtype=np.float64)


def _trace(
    fold: int,
    training: int,
    held_out: int,
    fits: tuple[RobustFit | None, ...],
    *,
    failure: str | None,
    slope: float | None = None,
) -> FoldFitTrace:
    full, rna, cnv = fits
    rounded_slope = None if slope is None else round(slope, 8)
    return FoldFitTrace(
        fold=fold,
        training_complete=training,
        held_out_complete=held_out,
        full_iterations=None if full is None else full.iterations,
        rna_only_iterations=None if rna is None else rna.iterations,
        cnv_only_iterations=None if cnv is None else cnv.iterations,
        full_converged=full is not None and full.converged,
        rna_only_converged=rna is not None and rna.converged,
        cnv_only_converged=cnv is not None and cnv.converged,
        conditional_rna_slope=0.0 if rounded_slope == 0.0 else rounded_slope,
        valid=failure is None,
        failure_reason=failure,
    )


def refit_point_with_budget(
    cnv: object, rna: object, protein: object, folds: object, *, max_iterations: int
) -> BudgetPointRefit:
    """Reproduce the legacy point equations and gates, preserving supplied order.

    The helper does not sort bootstrap draws. Its ``accepted`` field refers to
    the unchanged four-fold/sixty-OOF support gates only; the continuation caller
    must additionally apply the legacy point-summary and bootstrap gates.
    """

    if type(max_iterations) is not int:
        raise TypeError("max_iterations must be an exact integer")
    if max_iterations not in ALLOWED_ITERATION_BUDGETS:
        raise ValueError("max_iterations must be one of 30, 60, 120, or 240")
    cnv_values, rna_values, protein_values, fold_values = _arrays(cnv, rna, protein, folds)
    complete = np.isfinite(cnv_values) & np.isfinite(rna_values) & np.isfinite(protein_values)
    observed = np.full(len(protein_values), np.nan, dtype=np.float64)
    predictions = tuple(np.full(len(protein_values), np.nan, dtype=np.float64) for _ in range(4))
    traces = []
    slopes = []
    for fold in range(FOLD_COUNT):
        training, held_out = complete & (fold_values != fold), complete & (fold_values == fold)
        training_count, held_out_count = int(training.sum()), int(held_out.sum())
        fits: tuple[RobustFit | None, ...] = (None, None, None)
        failure = None
        slope = None
        if training_count < DEFAULT_MINIMUM_TRAIN_COMPLETE:
            failure = "insufficient training complete cases"
        elif held_out_count < DEFAULT_MINIMUM_TEST_COMPLETE:
            failure = "insufficient held-out complete cases"
        else:
            fits = (
                fit_huber_with_budget(
                    np.column_stack((rna_values[training], cnv_values[training])),
                    protein_values[training],
                    max_iterations=max_iterations,
                ),
                fit_huber_with_budget(
                    rna_values[training, None],
                    protein_values[training],
                    max_iterations=max_iterations,
                ),
                fit_huber_with_budget(
                    cnv_values[training, None],
                    protein_values[training],
                    max_iterations=max_iterations,
                ),
            )
            if any(fit is None for fit in fits):
                failure = "one or more fold models were numerically unidentified"
            elif any(not fit.converged for fit in fits if fit is not None):
                failure = "one or more fold models did not converge"
            else:
                full, rna, cnv_fit = fits
                if full is None or rna is None or cnv_fit is None:  # pragma: no cover
                    raise AssertionError("validated budget fits unexpectedly disappeared")
                denominator = float(full.x_scale[0])
                slope = (
                    float(full.y_scale * full.beta[1] / denominator)
                    if isfinite(denominator) and denominator > 1e-12
                    else None
                )
                if slope is None or not isfinite(slope):
                    failure = "conditional RNA slope could not be recovered on the raw scale"
                    slope = None
                else:
                    values = (
                        full.predict(np.column_stack((rna_values[held_out], cnv_values[held_out]))),
                        rna.predict(rna_values[held_out, None]),
                        cnv_fit.predict(cnv_values[held_out, None]),
                        np.full(
                            held_out_count, np.median(protein_values[training]), dtype=np.float64
                        ),
                    )
                    if any(not bool(np.all(np.isfinite(value))) for value in values):
                        failure = "one or more held-out predictions were non-finite"
                        slope = None
                    else:
                        observed[held_out] = protein_values[held_out]
                        for target, value in zip(predictions, values, strict=True):
                            target[held_out] = value
                        slopes.append(slope)
        traces.append(
            _trace(fold, training_count, held_out_count, fits, failure=failure, slope=slope)
        )
    count = int(np.isfinite(observed).sum())
    return BudgetPointRefit(
        max_iterations=max_iterations,
        complete_count=int(complete.sum()),
        valid_folds=len(slopes),
        oof_count=count,
        accepted=len(slopes) >= DEFAULT_MINIMUM_VALID_FOLDS and count >= DEFAULT_MINIMUM_OOF,
        raw_slopes=tuple(slopes),
        fold_trace=tuple(traces),
        observed=_immutable(observed),
        predictions=tuple(_immutable(value) for value in predictions),
    )


def _matched_metrics(
    truth: FloatArray, prediction: FloatArray, baseline: FloatArray
) -> MatchedReconstruction | None:
    if len(truth) < 3:
        return None
    residual = truth - prediction
    sse = float(np.dot(residual, residual))
    null_residual = truth - baseline
    null_sse = float(np.dot(null_residual, null_residual))
    return MatchedReconstruction(
        observed_count=len(truth),
        mae=float(np.mean(np.abs(residual))),
        rmse=sqrt(sse / len(truth)),
        r2_vs_fold_train_median=1.0 - sse / null_sse if null_sse > 1e-12 else None,
    )


def _audit_budget(point: BudgetPointRefit, common: npt.NDArray[np.bool_]) -> BudgetConvergenceAudit:
    traces = point.fold_trace
    metrics = tuple(
        _matched_metrics(point.observed[common], values[common], point.predictions[3][common])
        for values in point.predictions
    )
    return BudgetConvergenceAudit(
        max_iterations=point.max_iterations,
        accepted_fold_count=point.valid_folds,
        accepted_oof_count=point.oof_count,
        full_converged_fold_count=sum(trace.full_converged for trace in traces),
        rna_only_converged_fold_count=sum(trace.rna_only_converged for trace in traces),
        cnv_only_converged_fold_count=sum(trace.cnv_only_converged for trace in traces),
        full_iteration_cap_exhausted_count=sum(
            not trace.full_converged and trace.full_iterations == point.max_iterations
            for trace in traces
        ),
        rna_only_iteration_cap_exhausted_count=sum(
            not trace.rna_only_converged and trace.rna_only_iterations == point.max_iterations
            for trace in traces
        ),
        cnv_only_iteration_cap_exhausted_count=sum(
            not trace.cnv_only_converged and trace.cnv_only_iterations == point.max_iterations
            for trace in traces
        ),
        fold_trace=traces,
        common_oof_count=int(common.sum()),
        full_model=metrics[0],
        rna_only=metrics[1],
        cnv_only=metrics[2],
        training_median=metrics[3],
    )


def evaluate_convergence_budgets(
    cnv: object, rna: object, protein: object, folds: object
) -> ConvergenceBudgetEvaluation:
    """Compare all budgets on exactly the same complete OOF observations."""

    legacy = evaluate_gene_inputs(cnv, rna, protein, folds)
    cnv_values, rna_values, protein_values, fold_values = _arrays(cnv, rna, protein, folds)

    def numeric(value: float) -> tuple[int, float]:
        return (1, 0.0) if np.isnan(value) else (0, value)

    order = np.asarray(
        sorted(
            range(len(fold_values)),
            key=lambda index: (
                int(fold_values[index]),
                numeric(float(cnv_values[index])),
                numeric(float(rna_values[index])),
                numeric(float(protein_values[index])),
            ),
        ),
        dtype=np.int64,
    )
    inputs = cnv_values[order], rna_values[order], protein_values[order], fold_values[order]
    points = tuple(
        refit_point_with_budget(*inputs, max_iterations=budget)
        for budget in ALLOWED_ITERATION_BUDGETS
    )
    common_folds = tuple(
        fold for fold in range(FOLD_COUNT) if all(point.fold_trace[fold].valid for point in points)
    )
    common = np.logical_and.reduce(tuple(np.isfinite(point.observed) for point in points))
    common_count = int(common.sum())
    replay_agreement = all(
        original.point_fit_accepted == current.valid
        and original.training_complete == current.training_complete
        and original.held_out_complete == current.held_out_complete
        and original.full_iterations == current.full_iterations
        and original.rna_only_iterations == current.rna_only_iterations
        and original.cnv_only_iterations == current.cnv_only_iterations
        and bool(original.full_converged) == current.full_converged
        and bool(original.rna_only_converged) == current.rna_only_converged
        and bool(original.cnv_only_converged) == current.cnv_only_converged
        and original.failure_reason == current.failure_reason
        for original, current in zip(legacy.folds, points[0].fold_trace, strict=True)
    )
    sufficient = (
        common_count >= DEFAULT_MINIMUM_OOF and len(common_folds) >= DEFAULT_MINIMUM_VALID_FOLDS
    )
    return ConvergenceBudgetEvaluation(
        total_count=len(protein_values),
        complete_count=points[0].complete_count,
        compared_budgets=ALLOWED_ITERATION_BUDGETS,
        common_accepted_folds=common_folds,
        common_oof_count=common_count,
        minimum_common_oof=DEFAULT_MINIMUM_OOF,
        minimum_common_valid_folds=DEFAULT_MINIMUM_VALID_FOLDS,
        comparison_status="matched_support_sufficient"
        if sufficient
        else "descriptive_insufficient_common_support",
        legacy_30_point_fit_accepted=legacy.point_fit_accepted,
        legacy_30_fold_replay_agreement=replay_agreement,
        budgets=tuple(_audit_budget(point, common) for point in points),
        promotes_legacy_artifact=False,
        provides_new_bootstrap_evidence=False,
        limitations=(
            "Iteration budgets are numerical continuation sensitivity, not separate biological models or independent replication.",
            "All reported comparator errors use the intersection of folds accepted by every budget; additional recovered observations never improve a budget by changing evaluation support.",
            "Fewer than four common accepted folds or sixty common OOF observations is descriptive insufficient common support.",
            "Additional convergence does not establish coefficient identification, uncertainty calibration, external validity, or biological truth.",
            "No bootstrap, legacy artifact promotion, conditional-association label, or patient-level prediction is emitted by this audit.",
        ),
    )


__all__ = [
    "BudgetConvergenceAudit",
    "BudgetPointRefit",
    "ConvergenceBudgetEvaluation",
    "MatchedReconstruction",
    "evaluate_convergence_budgets",
    "refit_point_with_budget",
]

"""Deterministic cross-validated robust cis-dosage model.

The implementation is deliberately estimator-based: every outer fold learns
Huber-IRLS regressions from training data only, then evaluates held-out samples.
No patient data or fitted patient prediction is exposed by the runtime lane.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, cast

import numpy as np
import numpy.typing as npt

HUBER_K: Final = 1.345
MAX_IRLS_ITERATIONS: Final = 30
IRLS_TOLERANCE: Final = 1e-8
SLOPE_RIDGE: Final = 1e-8
MIN_TRAIN: Final = 48
MIN_TEST: Final = 3
MIN_VALID_FOLDS: Final = 4
MIN_OOF: Final = 60
QUANTIZATION_DECIMALS: Final = 8

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int8]


@dataclass(frozen=True, slots=True)
class RobustFit:
    x_center: FloatArray
    x_scale: FloatArray
    y_center: float
    y_scale: float
    beta: FloatArray
    converged: bool
    iterations: int

    def predict(self, x: FloatArray) -> FloatArray:
        standardized = (x - self.x_center) / self.x_scale
        design = np.column_stack((np.ones(len(standardized)), standardized))
        return np.asarray(self.y_center + self.y_scale * (design @ self.beta), dtype=float)


@dataclass(frozen=True, slots=True)
class GeneFit:
    rna: dict[str, int | float | None]
    protein: dict[str, int | float | None]
    protein_rna_only_r2: float | None
    protein_cnv_only_r2: float | None
    coefficients: dict[str, int | float | None]
    mechanism: str
    rna_evidence_gate: bool
    protein_evidence_gate: bool


def _median_scale(values: FloatArray) -> tuple[float, float] | None:
    center = float(np.median(values))
    scale = float(np.median(np.abs(values - center))) * 1.4826
    if not math.isfinite(scale) or scale < IRLS_TOLERANCE:
        scale = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    if not math.isfinite(scale) or scale < IRLS_TOLERANCE:
        return None
    return center, scale


def fit_huber(x: FloatArray, y: FloatArray) -> RobustFit | None:
    """Fit a robust linear model by deterministic Huber IRLS."""

    if x.ndim != 2 or y.ndim != 1 or len(x) != len(y) or len(y) < 3:
        raise ValueError("Huber inputs must be aligned finite matrices")
    if not bool(np.all(np.isfinite(x))) or not bool(np.all(np.isfinite(y))):
        raise ValueError("Huber fitting forbids non-finite complete-case inputs")
    scaled_columns = [_median_scale(x[:, column]) for column in range(x.shape[1])]
    if any(value is None for value in scaled_columns):
        return None
    response_scale = _median_scale(y)
    if response_scale is None:
        return None
    x_center = np.asarray([value[0] for value in scaled_columns if value is not None])
    x_scale = np.asarray([value[1] for value in scaled_columns if value is not None])
    y_center, y_scale = response_scale
    design = np.column_stack((np.ones(len(x)), (x - x_center) / x_scale))
    target = (y - y_center) / y_scale
    ridge = np.eye(design.shape[1]) * SLOPE_RIDGE
    ridge[0, 0] = 0.0
    try:
        beta = np.linalg.solve(design.T @ design + ridge, design.T @ target)
    except np.linalg.LinAlgError:
        return None
    converged = False
    iterations = 0
    for iteration in range(1, MAX_IRLS_ITERATIONS + 1):
        iterations = iteration
        residual = target - design @ beta
        scale = float(np.median(np.abs(residual - np.median(residual)))) * 1.4826
        if not math.isfinite(scale):
            return None
        if scale < IRLS_TOLERANCE:
            converged = True
            break
        standardized = np.abs(residual) / scale
        weights = np.ones_like(standardized)
        outliers = standardized > HUBER_K
        weights[outliers] = HUBER_K / standardized[outliers]
        weighted_design = design * weights[:, None]
        try:
            new_beta = np.linalg.solve(
                design.T @ weighted_design + ridge,
                weighted_design.T @ target,
            )
        except np.linalg.LinAlgError:
            return None
        if float(np.max(np.abs(new_beta - beta))) < IRLS_TOLERANCE:
            beta = new_beta
            converged = True
            break
        beta = new_beta
    return RobustFit(
        x_center=x_center,
        x_scale=x_scale,
        y_center=y_center,
        y_scale=y_scale,
        beta=np.asarray(beta, dtype=float),
        converged=converged,
        iterations=iterations,
    )


def _average_ranks(values: FloatArray) -> FloatArray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    left = 0
    while left < len(values):
        right = left + 1
        while right < len(values) and values[order[right]] == values[order[left]]:
            right += 1
        ranks[order[left:right]] = (left + right - 1) / 2.0 + 1.0
        left = right
    return ranks


def _correlation(left: FloatArray, right: FloatArray) -> float | None:
    if len(left) < 3 or float(np.std(left)) < 1e-12 or float(np.std(right)) < 1e-12:
        return None
    value = float(np.corrcoef(left, right)[0, 1])
    return value if math.isfinite(value) else None


def _sign_consistency(values: list[float]) -> float | None:
    finite = [value for value in values if math.isfinite(value) and abs(value) > 1e-10]
    if not finite:
        return None
    median = float(np.median(finite))
    if abs(median) <= 1e-10:
        return None
    sign = 1 if median > 0 else -1
    return sum((1 if value > 0 else -1) == sign for value in finite) / len(finite)


def _metrics(
    truth: FloatArray,
    prediction: FloatArray,
    null_prediction: FloatArray,
) -> dict[str, int | float | None] | None:
    valid = np.isfinite(truth) & np.isfinite(prediction) & np.isfinite(null_prediction)
    observed = truth[valid]
    predicted = prediction[valid]
    baseline = null_prediction[valid]
    if len(observed) < 3:
        return None
    baseline_sse = float(np.sum((observed - baseline) ** 2))
    model_sse = float(np.sum((observed - predicted) ** 2))
    r2 = 1.0 - model_sse / baseline_sse if baseline_sse > 1e-12 else None
    true_delta = observed - baseline
    predicted_delta = predicted - baseline
    directional = (np.abs(true_delta) > 1e-12) & (np.abs(predicted_delta) > 1e-12)
    direction = (
        float(np.mean(np.sign(true_delta[directional]) == np.sign(predicted_delta[directional])))
        if int(directional.sum())
        else None
    )
    return {
        "n_oof": len(observed),
        "pearson": _correlation(observed, predicted),
        "spearman": _correlation(_average_ranks(observed), _average_ranks(predicted)),
        "r2_vs_fold_train_median": r2,
        "direction_accuracy_vs_fold_train_median": direction,
    }


def _mechanism(coefficients: dict[str, int | float | None]) -> str:
    indirect = cast("float", coefficients["indirect_a_times_b_median"])
    direct = cast("float", coefficients["cprime_cnv_to_protein_given_rna_median"])
    total = cast("float", coefficients["total_proxy_median"])
    stable_indirect = float(coefficients["indirect_sign_consistency"] or 0.0) >= 0.8
    stable_total = float(coefficients["total_sign_consistency"] or 0.0) >= 0.8
    stable_direct = float(coefficients["cprime_sign_consistency"] or 0.0) >= 0.8
    stable_b = float(coefficients["b_sign_consistency"] or 0.0) >= 0.8
    b_value = cast("float", coefficients["b_rna_to_protein_given_cnv_median"])
    if not (stable_indirect and stable_total):
        return "unstable_or_mixed"
    if stable_direct and indirect * direct < 0 and abs(total) < abs(indirect):
        return "buffered"
    if indirect * total < 0 or (stable_b and b_value < 0):
        return "discordant"
    if indirect * total > 0 and abs(indirect) >= 0.5 * abs(total):
        return "propagated"
    return "stable_other"


def _passes_evidence_gates(fit: GeneFit) -> tuple[bool, bool]:
    rna = fit.rna
    protein = fit.protein
    coefficient = fit.coefficients
    rna_positive = (
        float(rna["r2_vs_fold_train_median"] or -99.0) > 0.05
        and float(rna["pearson"] or -99.0) > 0.25
        and float(rna["direction_accuracy_vs_fold_train_median"] or -99.0) > 0.60
        and float(coefficient["a_sign_consistency"] or 0.0) >= 0.8
    )
    protein_positive = (
        float(protein["r2_vs_fold_train_median"] or -99.0) > 0.02
        and float(protein["pearson"] or -99.0) > 0.20
        and float(protein["direction_accuracy_vs_fold_train_median"] or -99.0) > 0.55
        and float(protein["delta_r2_vs_rna_only"] or -99.0) > 0.0
        and float(protein["delta_r2_vs_cnv_only"] or -99.0) > 0.0
        and float(coefficient["total_sign_consistency"] or 0.0) >= 0.8
    )
    return rna_positive, protein_positive


def fit_gene_cross_validated(  # noqa: PLR0915 - locked oracle is intentionally stepwise.
    cnv: npt.ArrayLike,
    rna: npt.ArrayLike,
    protein: npt.ArrayLike,
    folds: npt.ArrayLike,
    *,
    min_train: int = MIN_TRAIN,
    min_test: int = MIN_TEST,
) -> GeneFit | None:
    """Fit fold-local robust models and return only aggregate gene evidence."""

    cnv_array = np.asarray(cnv, dtype=float)
    rna_array = np.asarray(rna, dtype=float)
    protein_array = np.asarray(protein, dtype=float)
    fold_array = np.asarray(folds, dtype=np.int8)
    lengths = {len(cnv_array), len(rna_array), len(protein_array), len(fold_array)}
    if len(lengths) != 1 or cnv_array.ndim != 1 or len(cnv_array) < MIN_OOF:
        raise ValueError("gene matrices and folds must be aligned one-dimensional arrays")
    if set(np.unique(fold_array).tolist()).difference(range(5)):
        raise ValueError("folds must use only the integers zero through four")

    count = len(cnv_array)
    rna_prediction = np.full(count, np.nan)
    rna_null = np.full(count, np.nan)
    protein_full = np.full(count, np.nan)
    protein_rna = np.full(count, np.nan)
    protein_cnv = np.full(count, np.nan)
    protein_null = np.full(count, np.nan)
    a_folds: list[float] = []
    b_folds: list[float] = []
    cprime_folds: list[float] = []
    indirect_folds: list[float] = []
    total_folds: list[float] = []
    rna_valid = 0
    protein_valid = 0
    rna_converged = 0
    protein_converged = 0

    for fold in range(5):
        training_fold = fold_array != fold
        test_fold = fold_array == fold
        paired = np.isfinite(cnv_array) & np.isfinite(rna_array)
        train = training_fold & paired
        test = test_fold & paired
        if int(train.sum()) >= min_train and int(test.sum()) >= min_test:
            rna_fit = fit_huber(cnv_array[train, None], rna_array[train])
            if rna_fit is not None:
                rna_prediction[test] = rna_fit.predict(cnv_array[test, None])
                rna_null[test] = float(np.median(rna_array[train]))
                rna_valid += 1
                rna_converged += int(rna_fit.converged)

        complete = np.isfinite(cnv_array) & np.isfinite(rna_array) & np.isfinite(protein_array)
        train = training_fold & complete
        test = test_fold & complete
        if int(train.sum()) < min_train or int(test.sum()) < min_test:
            continue
        x_train = np.column_stack((cnv_array[train], rna_array[train]))
        x_test = np.column_stack((cnv_array[test], rna_array[test]))
        y_train = protein_array[train]
        full_fit = fit_huber(x_train, y_train)
        rna_only_fit = fit_huber(rna_array[train, None], y_train)
        cnv_only_fit = fit_huber(cnv_array[train, None], y_train)
        mediation_fit = fit_huber(cnv_array[train, None], rna_array[train])
        fold_fits = (full_fit, rna_only_fit, cnv_only_fit, mediation_fit)
        if any(item is None for item in fold_fits):
            continue
        full_fit = cast("RobustFit", full_fit)
        rna_only_fit = cast("RobustFit", rna_only_fit)
        cnv_only_fit = cast("RobustFit", cnv_only_fit)
        mediation_fit = cast("RobustFit", mediation_fit)
        protein_full[test] = full_fit.predict(x_test)
        protein_rna[test] = rna_only_fit.predict(rna_array[test, None])
        protein_cnv[test] = cnv_only_fit.predict(cnv_array[test, None])
        protein_null[test] = float(np.median(y_train))
        a = float(mediation_fit.beta[1])
        cprime = float(full_fit.beta[1])
        b = float(full_fit.beta[2])
        indirect = a * b
        total = indirect + cprime
        a_folds.append(a)
        b_folds.append(b)
        cprime_folds.append(cprime)
        indirect_folds.append(indirect)
        total_folds.append(total)
        protein_valid += 1
        protein_converged += int(all(item.converged for item in fold_fits if item is not None))

    if rna_valid < MIN_VALID_FOLDS or protein_valid < MIN_VALID_FOLDS:
        return None
    rna_metrics = _metrics(rna_array, rna_prediction, rna_null)
    full_metrics = _metrics(protein_array, protein_full, protein_null)
    rna_only_metrics = _metrics(protein_array, protein_rna, protein_null)
    cnv_only_metrics = _metrics(protein_array, protein_cnv, protein_null)
    if any(
        item is None for item in (rna_metrics, full_metrics, rna_only_metrics, cnv_only_metrics)
    ):
        return None
    rna_metrics = cast("dict[str, int | float | None]", rna_metrics)
    full_metrics = cast("dict[str, int | float | None]", full_metrics)
    rna_only_metrics = cast("dict[str, int | float | None]", rna_only_metrics)
    cnv_only_metrics = cast("dict[str, int | float | None]", cnv_only_metrics)
    if int(rna_metrics["n_oof"] or 0) < MIN_OOF or int(full_metrics["n_oof"] or 0) < MIN_OOF:
        return None
    r2_full = full_metrics["r2_vs_fold_train_median"]
    r2_rna = rna_only_metrics["r2_vs_fold_train_median"]
    r2_cnv = cnv_only_metrics["r2_vs_fold_train_median"]
    full_metrics["delta_r2_vs_rna_only"] = (
        float(r2_full) - float(r2_rna) if r2_full is not None and r2_rna is not None else None
    )
    full_metrics["delta_r2_vs_cnv_only"] = (
        float(r2_full) - float(r2_cnv) if r2_full is not None and r2_cnv is not None else None
    )
    coefficients: dict[str, int | float | None] = {
        "valid_rna_folds": rna_valid,
        "valid_protein_folds": protein_valid,
        "converged_rna_folds": rna_converged,
        "converged_protein_folds": protein_converged,
        "a_cnv_to_rna_median": float(np.median(a_folds)),
        "b_rna_to_protein_given_cnv_median": float(np.median(b_folds)),
        "cprime_cnv_to_protein_given_rna_median": float(np.median(cprime_folds)),
        "indirect_a_times_b_median": float(np.median(indirect_folds)),
        "total_proxy_median": float(np.median(total_folds)),
        "a_sign_consistency": _sign_consistency(a_folds),
        "b_sign_consistency": _sign_consistency(b_folds),
        "cprime_sign_consistency": _sign_consistency(cprime_folds),
        "indirect_sign_consistency": _sign_consistency(indirect_folds),
        "total_sign_consistency": _sign_consistency(total_folds),
        "a_fold_mad": float(np.median(np.abs(np.asarray(a_folds) - np.median(a_folds)))),
        "b_fold_mad": float(np.median(np.abs(np.asarray(b_folds) - np.median(b_folds)))),
        "cprime_fold_mad": float(
            np.median(np.abs(np.asarray(cprime_folds) - np.median(cprime_folds)))
        ),
    }
    provisional = GeneFit(
        rna=rna_metrics,
        protein=full_metrics,
        protein_rna_only_r2=float(r2_rna) if r2_rna is not None else None,
        protein_cnv_only_r2=float(r2_cnv) if r2_cnv is not None else None,
        coefficients=coefficients,
        mechanism=_mechanism(coefficients),
        rna_evidence_gate=False,
        protein_evidence_gate=False,
    )
    rna_gate, protein_gate = _passes_evidence_gates(provisional)
    return GeneFit(
        rna=rna_metrics,
        protein=full_metrics,
        protein_rna_only_r2=provisional.protein_rna_only_r2,
        protein_cnv_only_r2=provisional.protein_cnv_only_r2,
        coefficients=coefficients,
        mechanism=provisional.mechanism,
        rna_evidence_gate=rna_gate,
        protein_evidence_gate=protein_gate,
    )


def quantized(value: object) -> object:
    """Quantize fitted aggregates and reject non-finite values."""

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("fitted artifacts forbid non-finite values")
        return round(value, QUANTIZATION_DECIMALS)
    if isinstance(value, dict):
        return {str(key): quantized(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [quantized(item) for item in value]
    return value


def gene_fit_document(value: GeneFit) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        quantized(
            {
                "rna": value.rna,
                "protein": value.protein,
                "coefficients": value.coefficients,
                "mechanism": value.mechanism,
                "rna_evidence_gate": value.rna_evidence_gate,
                "protein_evidence_gate": value.protein_evidence_gate,
            }
        ),
    )


__all__ = [
    "GeneFit",
    "RobustFit",
    "fit_gene_cross_validated",
    "fit_huber",
    "gene_fit_document",
    "quantized",
]

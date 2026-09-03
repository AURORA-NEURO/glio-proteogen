"""Calibratable mismatch diagnostics for GBmap count mixtures.

Thresholds are deliberately not embedded here: a future admitted artifact must
derive them inside held-donor and whole-study folds.  This module supplies the
exact diagnostics and finite-sample calibration primitives without pretending
that the unfitted checkout has learned thresholds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Final

import numpy as np
import numpy.typing as npt

from .dm import (
    dirichlet_multinomial_log_likelihood,
    dirichlet_multinomial_per_count_nll,
    dm_probability_gradient,
    dm_probability_hessian_diagonal,
)
from .errors import GbmapInputError, GbmapNumericalError

_FLOAT: Final = np.float64
_SIMPLEX_FLOOR: Final = 1e-12
_SATURATED_MAX_ITERATIONS: Final = 500
_SATURATED_KKT_TOLERANCE: Final = 1e-6


@dataclass(frozen=True, slots=True)
class OodDiagnostics:
    selected_count_depth: int
    normalized_dm_deviance: float
    standardized_pearson_residual: float
    aitchison_residual: float
    unknown_mass: float


@dataclass(frozen=True, slots=True)
class UnknownMassCalibration:
    threshold: float
    finite_sample_candidate: float
    achieved_specificity: float
    omitted_family_sensitivity: float
    hard_ceiling: float
    hard_ceiling_preserves_specificity: bool


def _counts(values: npt.ArrayLike) -> tuple[npt.NDArray[np.int64], int]:
    raw = np.asarray(values, dtype=object)
    if raw.ndim != 1 or raw.size < 2:
        raise GbmapInputError("counts must be a one-dimensional vector with at least two genes")
    result: list[int] = []
    total = 0
    for value in raw:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
            raise GbmapInputError("counts must contain exact non-Boolean integers")
        converted = int(value)
        if converted < 0:
            raise GbmapInputError("counts must be non-negative")
        total += converted
        if total > np.iinfo(np.int64).max:
            raise GbmapInputError("total count exceeds int64")
        result.append(converted)
    if total <= 0:
        raise GbmapInputError("mismatch diagnostics require positive count depth")
    return np.asarray(result, dtype=np.int64), total


def _probabilities(
    values: npt.ArrayLike,
    *,
    expected_size: int,
) -> npt.NDArray[np.float64]:
    raw = np.asarray(values, dtype=object)
    if raw.ndim != 1 or raw.size != expected_size:
        raise GbmapInputError("probabilities must match the count gene axis")
    converted: list[float] = []
    for value in raw:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            raise GbmapInputError("probabilities must contain non-Boolean real values")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= 0.0:
            raise GbmapInputError("probabilities must be finite and strictly positive")
        converted.append(numeric)
    if not math.isclose(math.fsum(converted), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise GbmapInputError("probabilities must sum to one")
    return np.asarray(converted, dtype=_FLOAT)


def _unit_interval(value: float, *, name: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise GbmapInputError(f"{name} must lie in the closed unit interval")
    return numeric


def _floored_simplex(values: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    normalized = values / float(np.sum(values, dtype=_FLOAT))
    return _SIMPLEX_FLOOR + (1.0 - _SIMPLEX_FLOOR * values.size) * normalized


def _simplex_kkt(
    probabilities: npt.NDArray[np.float64],
    gradient: npt.NDArray[np.float64],
) -> float:
    active = probabilities > 10.0 * _SIMPLEX_FLOOR
    multiplier = float(np.mean(gradient[active]))
    active_error = float(np.max(np.abs(gradient[active] - multiplier)))
    inactive_error = 0.0
    if np.any(~active):
        inactive_error = float(np.max(np.maximum(multiplier - gradient[~active], 0.0)))
    return max(active_error, inactive_error)


def saturated_dm_probabilities(
    counts: npt.ArrayLike,
    concentration: float,
) -> npt.NDArray[np.float64]:
    """Fit the fixed-concentration DM saturated reference on the gene simplex."""

    count_values, total = _counts(counts)
    probability = _floored_simplex(count_values.astype(_FLOAT) + 0.5)
    objective = dirichlet_multinomial_per_count_nll(count_values, probability, concentration)
    step = 1.0
    converged = False
    for _ in range(_SATURATED_MAX_ITERATIONS):
        gradient = dm_probability_gradient(count_values, probability, concentration)
        kkt = _simplex_kkt(probability, gradient)
        centered = gradient - float(probability @ gradient)
        candidate_step = step
        accepted: npt.NDArray[np.float64] | None = None
        candidate_objective = math.inf
        for _ in range(60):
            log_candidate = np.log(probability) - candidate_step * centered
            log_candidate -= float(np.max(log_candidate))
            candidate = _floored_simplex(np.exp(np.maximum(log_candidate, -745.0)))
            candidate_objective = dirichlet_multinomial_per_count_nll(
                count_values,
                candidate,
                concentration,
            )
            if candidate_objective <= objective:
                accepted = candidate
                break
            candidate_step *= 0.5
        if accepted is None:
            converged = kkt <= _SATURATED_KKT_TOLERANCE
            break
        l1_step = math.fsum(float(value) for value in np.abs(accepted - probability))
        probability = accepted
        objective_change = abs(objective - candidate_objective)
        objective = candidate_objective
        step = min(candidate_step * 1.5, 64.0)
        if (
            objective_change <= 1e-12 * max(1.0, abs(objective))
            and l1_step <= 1e-10
            and _simplex_kkt(
                probability,
                dm_probability_gradient(count_values, probability, concentration),
            )
            <= _SATURATED_KKT_TOLERANCE
        ):
            converged = True
            break
    if not converged:
        raise GbmapNumericalError("saturated DM reference did not close its KKT conditions")
    probability.flags.writeable = False
    if total <= 0:  # pragma: no cover - guarded by _counts, retained as an invariant.
        raise GbmapNumericalError("saturated DM reference lost positive count depth")
    return probability


def normalized_dm_deviance(
    counts: npt.ArrayLike,
    fitted_probabilities: npt.ArrayLike,
    concentration: float,
) -> float:
    """Return twice the saturated-versus-fitted DM log-likelihood gap per count."""

    count_values, total = _counts(counts)
    fitted = _probabilities(fitted_probabilities, expected_size=count_values.size)
    saturated = saturated_dm_probabilities(count_values, concentration)
    reference_log_likelihood = dirichlet_multinomial_log_likelihood(
        count_values,
        saturated,
        concentration,
    )
    fitted_log_likelihood = dirichlet_multinomial_log_likelihood(
        count_values,
        fitted,
        concentration,
    )
    deviance = 2.0 * (reference_log_likelihood - fitted_log_likelihood) / total
    if deviance < -1e-12 or not math.isfinite(deviance):
        raise GbmapNumericalError("DM deviance violated saturated-reference dominance")
    return max(0.0, deviance)


def standardized_dm_pearson_residual(
    counts: npt.ArrayLike,
    fitted_probabilities: npt.ArrayLike,
    concentration: float,
) -> float:
    """Return the root-mean-square DM-standardized Pearson residual."""

    count_values, total = _counts(counts)
    fitted = _probabilities(fitted_probabilities, expected_size=count_values.size)
    phi = float(concentration)
    if not math.isfinite(phi) or phi <= 0.0:
        raise GbmapInputError("concentration must be finite and positive")
    expected = total * fitted
    variance = total * fitted * (1.0 - fitted) * (total + phi) / (1.0 + phi) + 1.0
    residual = math.sqrt(float(np.mean(((count_values - expected) ** 2) / variance)))
    if not math.isfinite(residual):
        raise GbmapNumericalError("standardized Pearson residual became non-finite")
    return residual


def aitchison_residual(
    counts: npt.ArrayLike,
    fitted_probabilities: npt.ArrayLike,
    *,
    count_pseudocount: float = 0.5,
) -> float:
    """Return RMS centered-log-ratio separation from a smoothed count composition."""

    count_values, total = _counts(counts)
    fitted = _probabilities(fitted_probabilities, expected_size=count_values.size)
    pseudocount = float(count_pseudocount)
    if not math.isfinite(pseudocount) or pseudocount <= 0.0:
        raise GbmapInputError("count pseudocount must be finite and positive")
    observed = (count_values + pseudocount) / (total + pseudocount * count_values.size)
    log_ratio = np.log(observed) - np.log(fitted)
    centered = log_ratio - float(np.mean(log_ratio))
    result = math.sqrt(float(np.mean(centered * centered)))
    if not math.isfinite(result):
        raise GbmapNumericalError("Aitchison residual became non-finite")
    return result


def evaluate_ood_diagnostics(
    counts: npt.ArrayLike,
    fitted_probabilities: npt.ArrayLike,
    *,
    concentration: float,
    unknown_mass: float,
) -> OodDiagnostics:
    """Compute threshold-free diagnostics for later held-out calibration."""

    count_values, total = _counts(counts)
    mass = _unit_interval(unknown_mass, name="unknown mass")
    return OodDiagnostics(
        selected_count_depth=total,
        normalized_dm_deviance=normalized_dm_deviance(
            count_values,
            fitted_probabilities,
            concentration,
        ),
        standardized_pearson_residual=standardized_dm_pearson_residual(
            count_values,
            fitted_probabilities,
            concentration,
        ),
        aitchison_residual=aitchison_residual(count_values, fitted_probabilities),
        unknown_mass=mass,
    )


def known_signature_tangent_condition_number(
    counts: npt.ArrayLike,
    fitted_probabilities: npt.ArrayLike,
    signatures: npt.ArrayLike,
    concentration: float,
) -> float:
    """Return DM-curvature conditioning of known signatures on their simplex tangent."""

    count_values, _ = _counts(counts)
    fitted = _probabilities(fitted_probabilities, expected_size=count_values.size)
    raw = np.asarray(signatures)
    if raw.dtype.kind not in "fiu" or raw.dtype.kind == "b":
        raise GbmapInputError("signatures must be a numeric matrix")
    matrix = np.asarray(raw, dtype=_FLOAT)
    if matrix.ndim != 2 or matrix.shape[0] != count_values.size or matrix.shape[1] < 1:
        raise GbmapInputError("signatures must have shape (genes, known lineages)")
    if not np.all(np.isfinite(matrix)) or np.any(matrix <= 0.0):
        raise GbmapInputError("signatures must be finite and strictly positive")
    if not np.allclose(np.sum(matrix, axis=0), 1.0, rtol=0.0, atol=1e-12):
        raise GbmapInputError("every signature must sum to one")
    if matrix.shape[1] == 1:
        return 1.0
    curvature = dm_probability_hessian_diagonal(count_values, fitted, concentration)
    contrasts = matrix[:, :-1] - matrix[:, [-1]]
    gram = contrasts.T @ (curvature[:, np.newaxis] * contrasts)
    eigenvalues = np.linalg.eigvalsh(gram)
    largest = float(eigenvalues[-1])
    smallest = float(eigenvalues[0])
    if largest <= 1e-12 or smallest <= max(1e-12, largest * np.finfo(_FLOAT).eps * 32.0):
        return math.inf
    condition = largest / smallest
    if not math.isfinite(condition):
        return math.inf
    return condition


def finite_sample_upper_quantile(values: npt.ArrayLike, coverage: float) -> float:
    """Return the conservative ``ceil((n+1)*coverage)`` order statistic."""

    requested = float(coverage)
    if not math.isfinite(requested) or not 0.0 < requested < 1.0:
        raise GbmapInputError("coverage must lie strictly between zero and one")
    raw = np.asarray(values, dtype=object)
    if raw.ndim != 1 or raw.size == 0:
        raise GbmapInputError("calibration values must be a nonempty vector")
    converted: list[float] = []
    for value in raw:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            raise GbmapInputError("calibration values must be non-Boolean real numbers")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise GbmapInputError("calibration values must be finite")
        converted.append(numeric)
    ordered = sorted(converted)
    rank = min(len(ordered), math.ceil((len(ordered) + 1) * requested))
    return ordered[rank - 1]


def calibrate_unknown_mass_threshold(
    known_reference_masses: npt.ArrayLike,
    omitted_family_masses: npt.ArrayLike,
    *,
    target_specificity: float = 0.95,
    hard_ceiling: float = 0.35,
) -> UnknownMassCalibration:
    """Calibrate an omission gate without allowing a threshold above the hard ceiling."""

    specificity_target = _unit_interval(target_specificity, name="target specificity")
    ceiling = _unit_interval(hard_ceiling, name="hard ceiling")
    known = np.asarray(known_reference_masses, dtype=_FLOAT)
    omitted = np.asarray(omitted_family_masses, dtype=_FLOAT)
    for name, values in (("known", known), ("omitted", omitted)):
        if values.ndim != 1 or values.size == 0:
            raise GbmapInputError(f"{name} unknown-mass calibration values must be nonempty")
        if not np.all(np.isfinite(values)) or np.any(values < 0.0) or np.any(values > 1.0):
            raise GbmapInputError(f"{name} unknown-mass values must lie in the unit interval")
    candidate = finite_sample_upper_quantile(known, specificity_target)
    threshold = min(candidate, ceiling)
    achieved_specificity = float(np.mean(known <= threshold))
    sensitivity = float(np.mean(omitted > threshold))
    return UnknownMassCalibration(
        threshold=threshold,
        finite_sample_candidate=candidate,
        achieved_specificity=achieved_specificity,
        omitted_family_sensitivity=sensitivity,
        hard_ceiling=ceiling,
        hard_ceiling_preserves_specificity=achieved_specificity >= specificity_target,
    )


__all__ = [
    "OodDiagnostics",
    "UnknownMassCalibration",
    "aitchison_residual",
    "calibrate_unknown_mass_threshold",
    "evaluate_ood_diagnostics",
    "finite_sample_upper_quantile",
    "known_signature_tangent_condition_number",
    "normalized_dm_deviance",
    "saturated_dm_probabilities",
    "standardized_dm_pearson_residual",
]

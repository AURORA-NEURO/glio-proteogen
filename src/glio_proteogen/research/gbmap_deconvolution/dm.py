"""Validated Dirichlet-multinomial likelihood, derivatives, and sampling."""

from __future__ import annotations

import math
from numbers import Integral, Real
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .errors import GbmapInputError, GbmapNumericalError
from .numerics import digamma, trigamma

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

_SIMPLEX_ABSOLUTE_TOLERANCE: Final = 1.0e-12
_MAX_COUNT: Final = int(np.iinfo(np.int64).max)
_DIRECT_RISING_FACTORIAL_LIMIT: Final = 256


def _counts_vector(counts: ArrayLike) -> tuple[IntArray, int]:
    try:
        raw = np.asarray(counts, dtype=object)
    except (TypeError, ValueError) as error:
        raise GbmapInputError("counts must be a rectangular one-dimensional array") from error
    if raw.ndim != 1 or raw.size == 0:
        raise GbmapInputError("counts must be a non-empty one-dimensional vector")

    converted: list[int] = []
    total = 0
    for item in raw:
        if isinstance(item, (float, np.floating)) and not math.isfinite(float(item)):
            raise GbmapInputError("counts must not contain non-finite values")
        if isinstance(item, (bool, np.bool_)) or not isinstance(item, Integral):
            raise GbmapInputError("counts must contain exact non-Boolean integers")
        count = int(item)
        if count < 0:
            raise GbmapInputError("counts must be non-negative")
        if count > _MAX_COUNT:
            raise GbmapInputError("an individual count exceeds the supported int64 range")
        converted.append(count)
        total += count
        if total > _MAX_COUNT:
            raise GbmapInputError("total count exceeds the supported int64 range")
    return np.asarray(converted, dtype=np.int64), total


def _probability_vector(
    probabilities: ArrayLike,
    *,
    expected_size: int | None = None,
) -> FloatArray:
    try:
        raw = np.asarray(probabilities, dtype=object)
    except (TypeError, ValueError) as error:
        raise GbmapInputError(
            "probabilities must be a rectangular one-dimensional array"
        ) from error
    if raw.ndim != 1 or raw.size == 0:
        raise GbmapInputError("probabilities must be a non-empty one-dimensional vector")
    if expected_size is not None and raw.size != expected_size:
        raise GbmapInputError("counts and probabilities must have identical lengths")

    converted: list[float] = []
    for item in raw:
        if isinstance(item, (bool, np.bool_)) or not isinstance(item, Real):
            raise GbmapInputError("probabilities must contain non-Boolean real values")
        try:
            probability = float(item)
        except (OverflowError, TypeError, ValueError) as error:
            raise GbmapInputError("a probability is outside float64 range") from error
        if not math.isfinite(probability) or probability <= 0.0:
            raise GbmapInputError("probabilities must be finite and strictly positive")
        converted.append(probability)

    total = math.fsum(converted)
    if not math.isclose(
        total,
        1.0,
        rel_tol=0.0,
        abs_tol=_SIMPLEX_ABSOLUTE_TOLERANCE,
    ):
        raise GbmapInputError("probabilities must sum to one within 1e-12")
    return np.asarray(converted, dtype=np.float64)


def _positive_concentration(concentration: object) -> float:
    if isinstance(concentration, (bool, np.bool_)) or not isinstance(concentration, Real):
        raise GbmapInputError("concentration must be a non-Boolean real scalar")
    try:
        value = float(concentration)
    except (OverflowError, TypeError, ValueError) as error:
        raise GbmapInputError("concentration is outside float64 range") from error
    if not math.isfinite(value) or value <= 0.0:
        raise GbmapInputError("concentration must be finite and strictly positive")
    return value


def _model_inputs(
    counts: ArrayLike,
    probabilities: ArrayLike,
    concentration: float,
) -> tuple[IntArray, FloatArray, float, int]:
    count_values, total = _counts_vector(counts)
    probability_values = _probability_vector(probabilities, expected_size=count_values.size)
    concentration_value = _positive_concentration(concentration)
    alpha = concentration_value * probability_values
    if not bool(np.all(np.isfinite(alpha))) or not bool(np.all(alpha > 0.0)):
        raise GbmapInputError(
            "concentration and probabilities must produce finite positive parameters"
        )
    return count_values, probability_values, concentration_value, total


def _log_gamma(value: float) -> float:
    try:
        result = math.lgamma(value)
    except (OverflowError, ValueError) as error:
        raise GbmapNumericalError("Dirichlet-multinomial log-gamma term is invalid") from error
    if not math.isfinite(result):
        raise GbmapNumericalError("Dirichlet-multinomial log-gamma term is non-finite")
    return result


def _log_rising_factorial(base: float, increment: int) -> float:
    if increment <= _DIRECT_RISING_FACTORIAL_LIMIT:
        return math.fsum(math.log(base + offset) for offset in range(increment))
    result = _log_gamma(base + increment) - _log_gamma(base)
    if not math.isfinite(result):
        raise GbmapNumericalError("Dirichlet-multinomial rising factorial is non-finite")
    return result


def dirichlet_multinomial_log_likelihood(
    counts: ArrayLike,
    probabilities: ArrayLike,
    concentration: float,
) -> float:
    """Return the exact log PMF, including the multinomial coefficient.

    ``probabilities`` is the strictly positive simplex mean and
    ``concentration`` is the total Dirichlet concentration. Terms are produced
    in feature order and reduced with :func:`math.fsum` for deterministic scalar
    behavior.
    """

    count_values, probability_values, concentration_value, total = _model_inputs(
        counts,
        probabilities,
        concentration,
    )
    terms = [
        _log_gamma(total + 1),
        -_log_rising_factorial(concentration_value, total),
    ]
    for count, probability in zip(count_values, probability_values, strict=True):
        alpha = concentration_value * float(probability)
        terms.extend(
            (
                -_log_gamma(int(count) + 1),
                _log_rising_factorial(alpha, int(count)),
            )
        )
    try:
        result = math.fsum(terms)
    except (OverflowError, ValueError) as error:
        raise GbmapNumericalError(
            "Dirichlet-multinomial likelihood reduction is invalid"
        ) from error
    if not math.isfinite(result):
        raise GbmapNumericalError("Dirichlet-multinomial log likelihood is non-finite")
    return result


def dirichlet_multinomial_per_count_nll(
    counts: ArrayLike,
    probabilities: ArrayLike,
    concentration: float,
) -> float:
    """Return the negative log PMF divided by the positive total count."""

    count_values, _, _, total = _model_inputs(counts, probabilities, concentration)
    if total == 0:
        raise GbmapInputError("per-count NLL is undefined for zero total count")
    return (
        -dirichlet_multinomial_log_likelihood(
            count_values,
            probabilities,
            concentration,
        )
        / total
    )


def dm_probability_gradient(
    counts: ArrayLike,
    probabilities: ArrayLike,
    concentration: float,
) -> FloatArray:
    """Return the per-count NLL gradient with respect to simplex probabilities.

    The total concentration is fixed, so component ``g`` is
    ``phi/N * (digamma(phi*q[g]) - digamma(x[g] + phi*q[g]))``.
    """

    count_values, probability_values, concentration_value, total = _model_inputs(
        counts,
        probabilities,
        concentration,
    )
    if total == 0:
        raise GbmapInputError("per-count gradient is undefined for zero total count")
    alpha = concentration_value * probability_values
    initial = np.asarray(digamma(alpha), dtype=np.float64)
    updated = np.asarray(digamma(alpha + count_values), dtype=np.float64)
    result = (concentration_value / total) * (initial - updated)
    if not bool(np.all(np.isfinite(result))):
        raise GbmapNumericalError("Dirichlet-multinomial gradient is non-finite")
    return np.ascontiguousarray(result, dtype=np.float64)


def dm_probability_hessian_diagonal(
    counts: ArrayLike,
    probabilities: ArrayLike,
    concentration: float,
) -> FloatArray:
    """Return the diagonal per-count NLL Hessian with respect to probabilities."""

    count_values, probability_values, concentration_value, total = _model_inputs(
        counts,
        probabilities,
        concentration,
    )
    if total == 0:
        raise GbmapInputError("per-count Hessian is undefined for zero total count")
    alpha = concentration_value * probability_values
    initial = np.asarray(trigamma(alpha), dtype=np.float64)
    updated = np.asarray(trigamma(alpha + count_values), dtype=np.float64)
    result = (concentration_value * concentration_value / total) * (initial - updated)
    if not bool(np.all(np.isfinite(result))):
        raise GbmapNumericalError("Dirichlet-multinomial Hessian is non-finite")
    if bool(np.any(result < -32.0 * np.finfo(np.float64).eps)):
        raise GbmapNumericalError("Dirichlet-multinomial Hessian lost convexity")
    result[result < 0.0] = 0.0
    return np.ascontiguousarray(result, dtype=np.float64)


def _non_negative_total_count(total_count: object) -> int:
    if isinstance(total_count, (bool, np.bool_)) or not isinstance(total_count, Integral):
        raise GbmapInputError("total_count must be an exact non-Boolean integer")
    value = int(total_count)
    if value < 0 or value > _MAX_COUNT:
        raise GbmapInputError("total_count must be non-negative and fit in int64")
    return value


def sample_dirichlet_multinomial(
    total_count: int,
    probabilities: ArrayLike,
    concentration: float,
    rng: np.random.Generator,
) -> IntArray:
    """Draw one DM count vector using only the provided NumPy generator."""

    count = _non_negative_total_count(total_count)
    probability_values = _probability_vector(probabilities)
    concentration_value = _positive_concentration(concentration)
    if not isinstance(rng, np.random.Generator):
        raise GbmapInputError("rng must be an explicit numpy.random.Generator")
    alpha = concentration_value * probability_values
    if not bool(np.all(np.isfinite(alpha))) or not bool(np.all(alpha > 0.0)):
        raise GbmapInputError(
            "concentration and probabilities must produce finite positive parameters"
        )
    if count == 0:
        return np.zeros(probability_values.size, dtype=np.int64)

    try:
        latent_probability = rng.dirichlet(alpha)
        sample = rng.multinomial(count, latent_probability)
    except (FloatingPointError, OverflowError, ValueError) as error:
        raise GbmapNumericalError("Dirichlet-multinomial sampling failed") from error
    result = np.ascontiguousarray(sample, dtype=np.int64)
    if bool(np.any(result < 0)) or sum(int(item) for item in result) != count:
        raise GbmapNumericalError("Dirichlet-multinomial sample violates count invariants")
    return result


__all__ = [
    "FloatArray",
    "IntArray",
    "dirichlet_multinomial_log_likelihood",
    "dirichlet_multinomial_per_count_nll",
    "dm_probability_gradient",
    "dm_probability_hessian_diagonal",
    "sample_dirichlet_multinomial",
]

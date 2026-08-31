"""Small, deterministic special-function kernels used by GBmap.

Only the positive-real domain needed by the Dirichlet-multinomial model is
implemented.  Recurrence moves each argument to at least eight before a
fixed-order Bernoulli asymptotic expansion is evaluated.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .errors import GbmapInputError, GbmapNumericalError

FloatArray = NDArray[np.float64]

_ASYMPTOTIC_START: Final = 8.0
_DIGAMMA_COEFFICIENTS: Final[tuple[float, ...]] = (
    -1.0 / 12.0,
    1.0 / 120.0,
    -1.0 / 252.0,
    1.0 / 240.0,
    -1.0 / 132.0,
    691.0 / 32760.0,
    -1.0 / 12.0,
)
_TRIGAMMA_COEFFICIENTS: Final[tuple[float, ...]] = (
    1.0 / 6.0,
    -1.0 / 30.0,
    1.0 / 42.0,
    -1.0 / 30.0,
    5.0 / 66.0,
    -691.0 / 2730.0,
    7.0 / 6.0,
)


def _positive_real_array(value: ArrayLike, *, name: str) -> tuple[FloatArray, bool]:
    try:
        raw = np.asarray(value, dtype=object)
    except (TypeError, ValueError) as error:
        raise GbmapInputError(f"{name} must be a scalar or rectangular real array") from error
    if raw.size == 0:
        raise GbmapInputError(f"{name} must not be empty")

    converted: list[float] = []
    for item in raw.reshape(-1):
        if isinstance(item, (bool, np.bool_)) or not isinstance(item, Real):
            raise GbmapInputError(f"{name} must contain only non-Boolean real values")
        try:
            numeric = float(item)
        except (OverflowError, TypeError, ValueError) as error:
            raise GbmapInputError(f"{name} contains a value outside float64 range") from error
        if not math.isfinite(numeric) or numeric <= 0.0:
            raise GbmapInputError(f"{name} must contain only finite positive values")
        converted.append(numeric)

    values = np.asarray(converted, dtype=np.float64).reshape(raw.shape)
    return values, raw.ndim == 0


def _horner(inverse_square: FloatArray, coefficients: tuple[float, ...]) -> FloatArray:
    result = np.full_like(inverse_square, coefficients[-1])
    for coefficient in reversed(coefficients[:-1]):
        result = coefficient + inverse_square * result
    return result


def digamma(value: ArrayLike) -> float | FloatArray:
    """Return the logarithmic derivative of gamma for positive real inputs.

    Scalars produce a Python ``float``. Arrays preserve their input shape and
    produce a float64 array. Non-positive, Boolean, or non-finite values are
    rejected rather than invoking reflection across poles.
    """

    values, scalar = _positive_real_array(value, name="digamma argument")
    shape = values.shape
    shifted = values.reshape(-1).copy()
    result = np.zeros_like(shifted)

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        active = shifted < _ASYMPTOTIC_START
        while bool(np.any(active)):
            result[active] -= 1.0 / shifted[active]
            shifted[active] += 1.0
            active = shifted < _ASYMPTOTIC_START

        inverse = 1.0 / shifted
        inverse_square = inverse * inverse
        result += (
            np.log(shifted)
            - 0.5 * inverse
            + inverse_square * _horner(inverse_square, _DIGAMMA_COEFFICIENTS)
        )

    if not bool(np.all(np.isfinite(result))):
        raise GbmapNumericalError("digamma result is outside finite float64 range")
    reshaped = np.ascontiguousarray(result.reshape(shape), dtype=np.float64)
    if scalar:
        return float(reshaped.item())
    return reshaped


def trigamma(value: ArrayLike) -> float | FloatArray:
    """Return the first derivative of digamma for positive real inputs.

    Scalars produce a Python ``float``. Arrays preserve their input shape and
    produce a float64 array.
    """

    values, scalar = _positive_real_array(value, name="trigamma argument")
    shape = values.shape
    shifted = values.reshape(-1).copy()
    result = np.zeros_like(shifted)

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        active = shifted < _ASYMPTOTIC_START
        while bool(np.any(active)):
            result[active] += 1.0 / (shifted[active] * shifted[active])
            shifted[active] += 1.0
            active = shifted < _ASYMPTOTIC_START

        inverse = 1.0 / shifted
        inverse_square = inverse * inverse
        result += (
            inverse
            + 0.5 * inverse_square
            + inverse * inverse_square * _horner(inverse_square, _TRIGAMMA_COEFFICIENTS)
        )

    if not bool(np.all(np.isfinite(result))):
        raise GbmapNumericalError("trigamma result is outside finite float64 range")
    reshaped = np.ascontiguousarray(result.reshape(shape), dtype=np.float64)
    if scalar:
        return float(reshaped.item())
    return reshaped


__all__ = ["FloatArray", "digamma", "trigamma"]

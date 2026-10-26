"""Independent, explicitly bounded audit of the legacy adaptive-scale Huber solver.

This diagnostic reproduces the original numerical operations at a 30-iteration
budget and permits only three prespecified larger budgets. It does not replace
the 1.0 estimator, alter its profile, or establish that a recovered fit supports
any biological interpretation. Inputs, shared constants, and legacy functions
are never mutated.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.cptac_gbm_cis_dosage.model import RobustFit

ALLOWED_ITERATION_BUDGETS: Final = (30, 60, 120, 240)
_HUBER_CUTOFF: Final = 1.345
_MAD_MULTIPLIER: Final = 1.4826
_TOLERANCE: Final = 1e-8
_SLOPE_RIDGE: Final = 1e-8

FloatArray = npt.NDArray[np.float64]


def _center_scale(values: FloatArray) -> tuple[float, float] | None:
    center = float(np.median(values))
    scale = float(np.median(np.abs(values - center))) * _MAD_MULTIPLIER
    if not math.isfinite(scale) or scale < _TOLERANCE:
        scale = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    if not math.isfinite(scale) or scale < _TOLERANCE:
        return None
    return center, scale


def fit_huber_with_budget(
    x: FloatArray,
    y: FloatArray,
    *,
    max_iterations: int = 30,
) -> RobustFit | None:
    """Fit the unchanged adaptive-MAD IRLS equations with a declared iteration cap.

    A nonconverged, numerically evaluable fit is returned with ``converged=False``
    and its exact iteration count. Degenerate scales or failed linear solves
    return ``None``. Nonfinite or misaligned inputs and unapproved budgets raise.
    The budget must be an exact Python integer, excluding Boolean values.
    """

    if type(max_iterations) is not int:
        raise TypeError("max_iterations must be an exact integer")
    if max_iterations not in ALLOWED_ITERATION_BUDGETS:
        raise ValueError("max_iterations must be one of 30, 60, 120, or 240")
    if not isinstance(x, np.ndarray) or not isinstance(y, np.ndarray):
        raise TypeError("Huber inputs must be NumPy arrays")
    if x.ndim != 2 or y.ndim != 1 or len(x) != len(y) or len(y) < 3:
        raise ValueError("Huber inputs must be aligned finite matrices")
    if not bool(np.all(np.isfinite(x))) or not bool(np.all(np.isfinite(y))):
        raise ValueError("Huber fitting forbids non-finite complete-case inputs")

    column_scales = [_center_scale(x[:, column]) for column in range(x.shape[1])]
    if any(value is None for value in column_scales):
        return None
    response_scale = _center_scale(y)
    if response_scale is None:
        return None
    x_center = np.asarray([value[0] for value in column_scales if value is not None])
    x_scale = np.asarray([value[1] for value in column_scales if value is not None])
    y_center, y_scale = response_scale
    design = np.column_stack((np.ones(len(x)), (x - x_center) / x_scale))
    target = (y - y_center) / y_scale
    penalty = np.eye(design.shape[1]) * _SLOPE_RIDGE
    penalty[0, 0] = 0.0
    try:
        beta = np.linalg.solve(design.T @ design + penalty, design.T @ target)
    except np.linalg.LinAlgError:
        return None

    converged = False
    iterations = 0
    for iteration in range(1, max_iterations + 1):
        iterations = iteration
        residual = target - design @ beta
        residual_scale = float(np.median(np.abs(residual - np.median(residual))))
        residual_scale *= _MAD_MULTIPLIER
        if not math.isfinite(residual_scale):
            return None
        if residual_scale < _TOLERANCE:
            converged = True
            break
        standardized = np.abs(residual) / residual_scale
        weights = np.ones_like(standardized)
        outliers = standardized > _HUBER_CUTOFF
        weights[outliers] = _HUBER_CUTOFF / standardized[outliers]
        weighted_design = design * weights[:, None]
        try:
            updated = np.linalg.solve(
                design.T @ weighted_design + penalty,
                weighted_design.T @ target,
            )
        except np.linalg.LinAlgError:
            return None
        if float(np.max(np.abs(updated - beta))) < _TOLERANCE:
            beta = updated
            converged = True
            break
        beta = updated

    return RobustFit(
        x_center=x_center,
        x_scale=x_scale,
        y_center=y_center,
        y_scale=y_scale,
        beta=np.asarray(beta, dtype=float),
        converged=converged,
        iterations=iterations,
    )


__all__ = ["ALLOWED_ITERATION_BUDGETS", "fit_huber_with_budget"]

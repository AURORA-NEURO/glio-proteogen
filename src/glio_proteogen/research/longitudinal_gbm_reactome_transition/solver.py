"""Pure deterministic robust solver for conditional transition coordinates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Final, Literal

import numpy as np
from numpy.typing import NDArray

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .errors import ReactomeConditionalInferenceError

BoundSemantics = Literal["exact_delta", "upper_bound", "lower_bound"]
FloatMatrix = NDArray[np.float64]

HUBER_K: Final = 1.345
RIDGE_LAMBDA: Final = 1.0
GLOBAL_RIDGE_MULTIPLIER: Final = 0.25
DAMPING: Final = 0.7
MAX_ITERATIONS: Final = 200
TOLERANCE: Final = 1.0e-9
OBJECTIVE_INCREASE_TOLERANCE: Final = 1.0e-10


@dataclass(frozen=True, slots=True)
class SolverEvidence:
    """One standardized exact value or one-sided delta bound."""

    feature_position: int
    value: float
    semantics: BoundSemantics
    reliability_weight: float


@dataclass(frozen=True, slots=True)
class ConditionalSolverDiagnostics:
    """Convergence and objective evidence for one convex solve."""

    converged: bool
    iterations: int
    final_max_coordinate_change: float
    initial_objective: float
    final_objective: float
    objective_trace: tuple[float, ...]
    objective_monotone: bool
    active_evidence_count: int
    exact_evidence_count: int
    upper_bound_count: int
    lower_bound_count: int
    design_condition_number: float


@dataclass(frozen=True, slots=True)
class ConditionalSolveResult:
    """Coordinates and diagnostics returned by the robust solver."""

    coordinates: tuple[float, ...]
    diagnostics: ConditionalSolverDiagnostics


def _huber(values: FloatMatrix, delta: float) -> FloatMatrix:
    absolute = np.abs(values)
    return np.where(
        absolute <= delta,
        0.5 * values * values,
        delta * (absolute - 0.5 * delta),
    )


def _active_residuals(
    predictions: FloatMatrix,
    values: FloatMatrix,
    semantics: tuple[BoundSemantics, ...],
) -> tuple[FloatMatrix, NDArray[np.bool_]]:
    residual = predictions - values
    active = np.ones(residual.size, dtype=np.bool_)
    for index, item in enumerate(semantics):
        if item == "upper_bound":
            active[index] = residual[index] > 0.0
        elif item == "lower_bound":
            active[index] = residual[index] < 0.0
    return residual, active


def _objective(
    design: FloatMatrix,
    values: FloatMatrix,
    semantics: tuple[BoundSemantics, ...],
    reliability: FloatMatrix,
    coordinates: FloatMatrix,
    *,
    penalty: FloatMatrix,
    huber_k: float,
    ridge_lambda: float,
) -> float:
    residual, active = _active_residuals(design @ coordinates, values, semantics)
    data_loss = float(np.sum(reliability[active] * _huber(residual[active], huber_k)))
    ridge = 0.5 * ridge_lambda * float(coordinates @ penalty @ coordinates)
    return data_loss + ridge


def _validate_inputs(
    design: FloatMatrix,
    evidence: tuple[SolverEvidence, ...],
) -> None:
    if design.ndim != 2 or design.shape[0] == 0 or design.shape[1] == 0:
        raise ReactomeConditionalInferenceError("solver design must be a non-empty matrix")
    if not np.all(np.isfinite(design)):
        raise ReactomeConditionalInferenceError("solver design contains non-finite values")
    if not evidence:
        raise ReactomeConditionalInferenceError("solver requires active evidence")
    positions = tuple(item.feature_position for item in evidence)
    if len(set(positions)) != len(positions):
        raise ReactomeConditionalInferenceError("solver evidence positions are duplicated")
    for item in evidence:
        if not 0 <= item.feature_position < design.shape[0]:
            raise ReactomeConditionalInferenceError("solver evidence position is out of range")
        if (
            not math.isfinite(item.value)
            or not math.isfinite(item.reliability_weight)
            or item.reliability_weight <= 0.0
        ):
            raise ReactomeConditionalInferenceError(
                "solver evidence values and reliability weights must be finite and positive"
            )
        if item.semantics not in {"exact_delta", "upper_bound", "lower_bound"}:
            raise ReactomeConditionalInferenceError("unsupported solver evidence semantics")


def solve_conditional_coordinates(
    design: FloatMatrix,
    evidence: tuple[SolverEvidence, ...],
    *,
    huber_k: float = HUBER_K,
    ridge_lambda: float = RIDGE_LAMBDA,
    global_ridge_multiplier: float = GLOBAL_RIDGE_MULTIPLIER,
    damping: float = DAMPING,
    max_iterations: int = MAX_ITERATIONS,
    tolerance: float = TOLERANCE,
    cancellation: CancellationContext | None = None,
) -> ConditionalSolveResult:
    """Solve the convex robust coordinate problem without imputing missing evidence."""

    _validate_inputs(design, evidence)
    if (
        not math.isfinite(huber_k)
        or huber_k <= 0.0
        or not math.isfinite(ridge_lambda)
        or ridge_lambda <= 0.0
        or not math.isfinite(global_ridge_multiplier)
        or global_ridge_multiplier <= 0.0
        or not 0.0 < damping <= 1.0
        or max_iterations < 1
        or not math.isfinite(tolerance)
        or tolerance <= 0.0
    ):
        raise ReactomeConditionalInferenceError("solver constants are outside their domain")

    positions = np.asarray([item.feature_position for item in evidence], dtype=np.int64)
    active_design = np.ascontiguousarray(design[positions], dtype=np.float64)
    values = np.asarray([item.value for item in evidence], dtype=np.float64)
    reliability = np.asarray(
        [item.reliability_weight for item in evidence], dtype=np.float64
    )
    semantics = tuple(item.semantics for item in evidence)
    penalty = np.eye(active_design.shape[1], dtype=np.float64)
    penalty[0, 0] = global_ridge_multiplier
    coordinates = np.zeros(active_design.shape[1], dtype=np.float64)
    objective_trace = [
        _objective(
            active_design,
            values,
            semantics,
            reliability,
            coordinates,
            penalty=penalty,
            huber_k=huber_k,
            ridge_lambda=ridge_lambda,
        )
    ]
    final_change = math.inf
    converged = False
    iterations = 0
    for iteration in range(1, max_iterations + 1):
        checkpoint(cancellation)
        iterations = iteration
        residual, active = _active_residuals(
            active_design @ coordinates,
            values,
            semantics,
        )
        robust = np.zeros(residual.size, dtype=np.float64)
        robust[active] = np.minimum(
            1.0,
            huber_k / np.maximum(np.abs(residual[active]), 1.0e-12),
        )
        weights = reliability * robust
        system = (
            active_design.T @ (weights[:, None] * active_design)
            + ridge_lambda * penalty
        )
        target = active_design.T @ (weights * values)
        try:
            updated = np.linalg.solve(system, target)
        except np.linalg.LinAlgError as error:
            raise ReactomeConditionalInferenceError(
                "conditional coordinate system is singular"
            ) from error
        if not np.all(np.isfinite(updated)):
            raise ReactomeConditionalInferenceError(
                "conditional coordinate solve produced non-finite values"
            )
        final_change = float(np.max(np.abs(updated - coordinates)))
        if final_change < tolerance:
            coordinates = updated
            objective_trace.append(
                _objective(
                    active_design,
                    values,
                    semantics,
                    reliability,
                    coordinates,
                    penalty=penalty,
                    huber_k=huber_k,
                    ridge_lambda=ridge_lambda,
                )
            )
            converged = True
            break
        coordinates = damping * updated + (1.0 - damping) * coordinates
        objective_trace.append(
            _objective(
                active_design,
                values,
                semantics,
                reliability,
                coordinates,
                penalty=penalty,
                huber_k=huber_k,
                ridge_lambda=ridge_lambda,
            )
        )
    checkpoint(cancellation)
    monotone = all(
        right <= left + OBJECTIVE_INCREASE_TOLERANCE * max(1.0, abs(left))
        for left, right in pairwise(objective_trace)
    )
    condition = float(np.linalg.cond(active_design))
    # LAPACK may encode an exactly rank-deficient design as either infinity or
    # a very large finite condition number. Apply an explicit numerical-rank
    # cutoff so the diagnostic has the same semantics on every runner.
    singular_values = np.linalg.svd(active_design, compute_uv=False)
    rank_tolerance = np.finfo(np.float64).eps * max(active_design.shape) * float(singular_values[0])
    rank_deficient = float(singular_values[-1]) <= rank_tolerance
    if rank_deficient:
        condition = math.inf
    if not math.isfinite(condition):
        condition = math.inf
    return ConditionalSolveResult(
        coordinates=tuple(float(value) for value in coordinates),
        diagnostics=ConditionalSolverDiagnostics(
            converged=converged,
            iterations=iterations,
            final_max_coordinate_change=final_change,
            initial_objective=objective_trace[0],
            final_objective=objective_trace[-1],
            objective_trace=tuple(objective_trace),
            objective_monotone=monotone,
            active_evidence_count=len(evidence),
            exact_evidence_count=sum(item == "exact_delta" for item in semantics),
            upper_bound_count=sum(item == "upper_bound" for item in semantics),
            lower_bound_count=sum(item == "lower_bound" for item in semantics),
            design_condition_number=condition,
        ),
    )


__all__ = [
    "BoundSemantics",
    "ConditionalSolveResult",
    "ConditionalSolverDiagnostics",
    "SolverEvidence",
    "solve_conditional_coordinates",
]

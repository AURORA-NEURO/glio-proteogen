"""Deterministic robust one-factor projection for complex-member evidence."""

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

from .errors import ComplexTransitionInferenceError

BoundSemantics = Literal["exact_delta", "upper_bound", "lower_bound"]
FloatArray = NDArray[np.float64]

HUBER_K: Final = 1.345
RIDGE_LAMBDA: Final = 0.075
DAMPING: Final = 0.7
MAX_ITERATIONS: Final = 200
TOLERANCE: Final = 1.0e-9
OBJECTIVE_INCREASE_TOLERANCE: Final = 1.0e-10
MIN_INFORMATION: Final = 1.0e-12


@dataclass(frozen=True, slots=True)
class MemberEvidence:
    """One standardized exact member transition or one-sided transition bound."""

    member_position: int
    value: float
    semantics: BoundSemantics
    reliability_weight: float


@dataclass(frozen=True, slots=True)
class MemberCoordinateDiagnostics:
    converged: bool
    iterations: int
    final_coordinate_change: float
    initial_objective: float
    final_objective: float
    objective_trace: tuple[float, ...]
    objective_monotone: bool
    active_evidence_count: int
    exact_evidence_count: int
    upper_bound_count: int
    lower_bound_count: int
    weighted_information: float
    backtracking_step_count: int


@dataclass(frozen=True, slots=True)
class MemberCoordinateSolve:
    coordinate: float
    diagnostics: MemberCoordinateDiagnostics


def _huber(values: FloatArray, delta: float) -> FloatArray:
    absolute = np.abs(values)
    return np.where(
        absolute <= delta,
        0.5 * values * values,
        delta * (absolute - 0.5 * delta),
    )


def _active_residuals(
    predictions: FloatArray,
    values: FloatArray,
    semantics: tuple[BoundSemantics, ...],
) -> tuple[FloatArray, NDArray[np.bool_]]:
    residual = predictions - values
    active = np.ones(residual.size, dtype=np.bool_)
    for index, item in enumerate(semantics):
        if item == "upper_bound":
            active[index] = residual[index] > 0.0
        elif item == "lower_bound":
            active[index] = residual[index] < 0.0
    return residual, active


def _objective(
    loading: FloatArray,
    values: FloatArray,
    semantics: tuple[BoundSemantics, ...],
    reliability: FloatArray,
    coordinate: float,
    *,
    huber_k: float,
    ridge_lambda: float,
) -> float:
    residual, active = _active_residuals(loading * coordinate, values, semantics)
    evidence_loss = float(np.sum(reliability[active] * _huber(residual[active], huber_k)))
    return evidence_loss + 0.5 * ridge_lambda * coordinate * coordinate


def _validate_inputs(loadings: FloatArray, evidence: tuple[MemberEvidence, ...]) -> None:
    if loadings.ndim != 1 or loadings.size == 0:
        raise ComplexTransitionInferenceError("member loading must be a non-empty vector")
    if not np.all(np.isfinite(loadings)) or not np.any(np.abs(loadings) > 0.0):
        raise ComplexTransitionInferenceError(
            "member loading must contain finite non-zero coefficients"
        )
    if not evidence:
        raise ComplexTransitionInferenceError("member-coordinate solver requires evidence")
    positions = tuple(item.member_position for item in evidence)
    if len(positions) != len(set(positions)):
        raise ComplexTransitionInferenceError("member evidence positions are duplicated")
    for item in evidence:
        if not 0 <= item.member_position < loadings.size:
            raise ComplexTransitionInferenceError("member evidence position is out of range")
        if (
            not math.isfinite(item.value)
            or not math.isfinite(item.reliability_weight)
            or item.reliability_weight <= 0.0
        ):
            raise ComplexTransitionInferenceError(
                "member evidence values and weights must be finite and positive"
            )
        if item.semantics not in {"exact_delta", "upper_bound", "lower_bound"}:
            raise ComplexTransitionInferenceError("unsupported member evidence semantics")


def _validate_constants(
    huber_k: float,
    ridge_lambda: float,
    damping: float,
    max_iterations: int,
    tolerance: float,
) -> None:
    if (
        not math.isfinite(huber_k)
        or huber_k <= 0.0
        or not math.isfinite(ridge_lambda)
        or ridge_lambda <= 0.0
        or not math.isfinite(damping)
        or not 0.0 < damping <= 1.0
        or max_iterations < 1
        or not math.isfinite(tolerance)
        or tolerance <= 0.0
    ):
        raise ComplexTransitionInferenceError("member solver constants are outside their domain")


def solve_member_coordinate(
    loadings: FloatArray,
    evidence: tuple[MemberEvidence, ...],
    *,
    huber_k: float = HUBER_K,
    ridge_lambda: float = RIDGE_LAMBDA,
    damping: float = DAMPING,
    max_iterations: int = MAX_ITERATIONS,
    tolerance: float = TOLERANCE,
    cancellation: CancellationContext | None = None,
) -> MemberCoordinateSolve:
    """Minimize a one-factor Huber objective while preserving censor bounds."""

    _validate_inputs(loadings, evidence)
    _validate_constants(huber_k, ridge_lambda, damping, max_iterations, tolerance)

    positions = np.asarray([item.member_position for item in evidence], dtype=np.int64)
    active_loading = np.ascontiguousarray(loadings[positions], dtype=np.float64)
    values = np.asarray([item.value for item in evidence], dtype=np.float64)
    reliability = np.asarray([item.reliability_weight for item in evidence], dtype=np.float64)
    semantics = tuple(item.semantics for item in evidence)
    coordinate = 0.0
    current_objective = _objective(
        active_loading,
        values,
        semantics,
        reliability,
        coordinate,
        huber_k=huber_k,
        ridge_lambda=ridge_lambda,
    )
    objective_trace = [current_objective]
    converged = False
    final_change = math.inf
    iterations = 0
    backtracking_steps = 0
    information = ridge_lambda

    for iteration in range(1, max_iterations + 1):
        checkpoint(cancellation)
        iterations = iteration
        residual, active = _active_residuals(
            active_loading * coordinate,
            values,
            semantics,
        )
        robust = np.zeros(residual.size, dtype=np.float64)
        robust[active] = np.minimum(
            1.0,
            huber_k / np.maximum(np.abs(residual[active]), 1.0e-12),
        )
        weights = reliability * robust
        information = float(np.dot(weights, active_loading * active_loading)) + ridge_lambda
        if not math.isfinite(information) or information <= MIN_INFORMATION:
            raise ComplexTransitionInferenceError(
                "member-coordinate system has insufficient finite information"
            )
        target = float(np.dot(weights * active_loading, values))
        raw_update = target / information
        if not math.isfinite(raw_update):
            raise ComplexTransitionInferenceError(
                "member-coordinate solve produced a non-finite update"
            )

        step = damping
        accepted = coordinate
        accepted_objective = current_objective
        while step >= 2.0**-24:
            candidate = coordinate + step * (raw_update - coordinate)
            candidate_objective = _objective(
                active_loading,
                values,
                semantics,
                reliability,
                candidate,
                huber_k=huber_k,
                ridge_lambda=ridge_lambda,
            )
            if candidate_objective <= current_objective + (
                OBJECTIVE_INCREASE_TOLERANCE * max(1.0, abs(current_objective))
            ):
                accepted = candidate
                accepted_objective = candidate_objective
                break
            step *= 0.5
            backtracking_steps += 1

        final_change = abs(accepted - coordinate)
        coordinate = accepted
        current_objective = accepted_objective
        objective_trace.append(current_objective)
        if final_change < tolerance:
            converged = True
            break

    checkpoint(cancellation)
    monotone = all(
        right <= left + OBJECTIVE_INCREASE_TOLERANCE * max(1.0, abs(left))
        for left, right in pairwise(objective_trace)
    )
    return MemberCoordinateSolve(
        coordinate=coordinate,
        diagnostics=MemberCoordinateDiagnostics(
            converged=converged,
            iterations=iterations,
            final_coordinate_change=final_change,
            initial_objective=objective_trace[0],
            final_objective=objective_trace[-1],
            objective_trace=tuple(objective_trace),
            objective_monotone=monotone,
            active_evidence_count=len(evidence),
            exact_evidence_count=sum(item == "exact_delta" for item in semantics),
            upper_bound_count=sum(item == "upper_bound" for item in semantics),
            lower_bound_count=sum(item == "lower_bound" for item in semantics),
            weighted_information=information,
            backtracking_step_count=backtracking_steps,
        ),
    )


__all__ = [
    "BoundSemantics",
    "MemberCoordinateDiagnostics",
    "MemberCoordinateSolve",
    "MemberEvidence",
    "solve_member_coordinate",
]

"""Constrained robust latent solver for GBM functional-proteotype evidence.

The four source axes are fitted jointly with an explicit sum-to-zero constraint.
Observed evidence contributes a two-sided Huber loss; left-censored evidence is
an upper bound and contributes only when the fitted value exceeds that bound.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

_FLOAT: Final = np.float64
_PARAMETER_COUNT: Final = 5
_AXIS_COUNT: Final = 4


@dataclass(frozen=True, slots=True)
class SolverConfiguration:
    """Numerical constants bound into the public algorithm profile."""

    huber_delta: float
    standard_error_floor: float
    axis_ridge: float
    intercept_ridge: float
    damping: float
    tolerance: float
    gradient_tolerance: float
    max_iterations: int
    backtracking_factor: float
    backtracking_steps: int
    objective_increase_tolerance: float

    def __post_init__(self) -> None:
        finite_positive = (
            self.huber_delta,
            self.standard_error_floor,
            self.axis_ridge,
            self.intercept_ridge,
            self.damping,
            self.tolerance,
            self.gradient_tolerance,
            self.backtracking_factor,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in finite_positive):
            raise ValueError("solver constants must be finite and positive")
        if self.damping > 1.0 or self.backtracking_factor >= 1.0:
            raise ValueError("damping must be at most one and backtracking below one")
        if self.max_iterations < 1 or self.backtracking_steps < 1:
            raise ValueError("solver iteration limits must be positive")
        if (
            not math.isfinite(self.objective_increase_tolerance)
            or self.objective_increase_tolerance < 0.0
        ):
            raise ValueError("objective tolerance must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class SolverObservation:
    """One source-mapped protein term admitted to the convex objective."""

    axis_index: int
    source_loading: float
    state: Literal["observed", "left_censored"]
    value: float
    standard_error: float
    quality_weight: float
    bootstrap_weight: float = 1.0

    def __post_init__(self) -> None:
        if self.axis_index not in range(_AXIS_COUNT):
            raise ValueError("axis index must identify one of four source axes")
        finite_values = (
            self.source_loading,
            self.value,
            self.standard_error,
            self.quality_weight,
            self.bootstrap_weight,
        )
        if any(not math.isfinite(value) for value in finite_values):
            raise ValueError("solver observations must be finite")
        if self.source_loading <= 0.0 or self.standard_error <= 0.0:
            raise ValueError("source loading and standard error must be positive")
        if self.quality_weight <= 0.0 or self.bootstrap_weight <= 0.0:
            raise ValueError("active evidence weights must be positive")


@dataclass(frozen=True, slots=True)
class ObjectiveTraceRecord:
    iteration: int
    baseline_objective: float
    candidate_objective: float
    accepted_objective: float
    damping: float
    accepted: bool


@dataclass(frozen=True, slots=True)
class SolverOutcome:
    intercept: float
    axis_values: tuple[float, float, float, float]
    converged: bool
    iterations: int
    objective: float
    final_gradient_norm: float
    maximum_candidate_update: float
    sum_to_zero_residual: float
    objective_trace: tuple[ObjectiveTraceRecord, ...]


def _scale(item: SolverObservation, configuration: SolverConfiguration) -> float:
    return math.sqrt(
        item.standard_error * item.standard_error
        + configuration.standard_error_floor * configuration.standard_error_floor
    )


def _huber_loss(residual: float, delta: float) -> float:
    magnitude = abs(residual)
    if magnitude <= delta:
        return 0.5 * residual * residual
    return delta * (magnitude - 0.5 * delta)


def _huber_psi(residual: float, delta: float) -> float:
    return min(max(residual, -delta), delta)


def _effective_residual(
    parameters: npt.NDArray[np.float64],
    item: SolverObservation,
    configuration: SolverConfiguration,
) -> float | None:
    fitted = float(parameters[0] + item.source_loading * parameters[item.axis_index + 1])
    if item.state == "left_censored" and fitted <= item.value:
        return None
    return (fitted - item.value) / _scale(item, configuration)


def objective(
    parameters: npt.NDArray[np.float64],
    observations: tuple[SolverObservation, ...],
    configuration: SolverConfiguration,
) -> float:
    """Evaluate the exact convex objective used for monotonicity checks."""

    if parameters.shape != (_PARAMETER_COUNT,) or not np.all(np.isfinite(parameters)):
        raise ValueError("solver parameter vector is invalid")
    total = 0.5 * configuration.intercept_ridge * float(parameters[0] ** 2)
    total += 0.5 * configuration.axis_ridge * float(parameters[1:] @ parameters[1:])
    for item in observations:
        residual = _effective_residual(parameters, item, configuration)
        if residual is None:
            continue
        total += (
            item.quality_weight
            * item.bootstrap_weight
            * _huber_loss(residual, configuration.huber_delta)
        )
    if not math.isfinite(total):
        raise FloatingPointError("functional-proteotype objective became non-finite")
    return total


def _irls_candidate(
    current: npt.NDArray[np.float64],
    observations: tuple[SolverObservation, ...],
    configuration: SolverConfiguration,
) -> npt.NDArray[np.float64]:
    hessian = np.diag(
        np.asarray(
            [configuration.intercept_ridge] + [configuration.axis_ridge] * _AXIS_COUNT,
            dtype=_FLOAT,
        )
    )
    rhs = np.zeros(_PARAMETER_COUNT, dtype=_FLOAT)
    for item in observations:
        scale = _scale(item, configuration)
        fitted = float(current[0] + item.source_loading * current[item.axis_index + 1])
        if item.state == "left_censored" and fitted <= item.value:
            continue
        residual = (fitted - item.value) / scale
        magnitude = abs(residual)
        huber_weight = (
            1.0
            if magnitude <= configuration.huber_delta or magnitude == 0.0
            else configuration.huber_delta / magnitude
        )
        weight = item.quality_weight * item.bootstrap_weight * huber_weight / (scale * scale)
        axis_parameter = item.axis_index + 1
        weighted_loading = weight * item.source_loading
        hessian[0, 0] += weight
        hessian[0, axis_parameter] += weighted_loading
        hessian[axis_parameter, 0] += weighted_loading
        hessian[axis_parameter, axis_parameter] += weight * (
            item.source_loading * item.source_loading
        )
        weighted_value = weight * item.value
        rhs[0] += weighted_value
        rhs[axis_parameter] += weighted_loading * item.value

    constraint = np.zeros(_PARAMETER_COUNT, dtype=_FLOAT)
    constraint[1:] = 1.0
    kkt = np.zeros((_PARAMETER_COUNT + 1, _PARAMETER_COUNT + 1), dtype=_FLOAT)
    kkt[:_PARAMETER_COUNT, :_PARAMETER_COUNT] = hessian
    kkt[:_PARAMETER_COUNT, _PARAMETER_COUNT] = constraint
    kkt[_PARAMETER_COUNT, :_PARAMETER_COUNT] = constraint
    kkt_rhs = np.zeros(_PARAMETER_COUNT + 1, dtype=_FLOAT)
    kkt_rhs[:_PARAMETER_COUNT] = rhs
    try:
        solved = np.linalg.solve(kkt, kkt_rhs)[:_PARAMETER_COUNT]
    except np.linalg.LinAlgError as error:
        raise FloatingPointError("constrained IRLS system is singular") from error
    if not np.all(np.isfinite(solved)):
        raise FloatingPointError("constrained IRLS candidate became non-finite")
    return np.asarray(solved, dtype=_FLOAT)


def _projected_gradient(
    parameters: npt.NDArray[np.float64],
    observations: tuple[SolverObservation, ...],
    configuration: SolverConfiguration,
) -> npt.NDArray[np.float64]:
    gradient = np.zeros(_PARAMETER_COUNT, dtype=_FLOAT)
    gradient[0] = configuration.intercept_ridge * parameters[0]
    gradient[1:] = configuration.axis_ridge * parameters[1:]
    for item in observations:
        scale = _scale(item, configuration)
        fitted = float(parameters[0] + item.source_loading * parameters[item.axis_index + 1])
        if item.state == "left_censored" and fitted <= item.value:
            continue
        residual = (fitted - item.value) / scale
        derivative = (
            item.quality_weight
            * item.bootstrap_weight
            * _huber_psi(residual, configuration.huber_delta)
            / scale
        )
        gradient[0] += derivative
        gradient[item.axis_index + 1] += derivative * item.source_loading
    gradient[1:] -= float(np.mean(gradient[1:]))
    return gradient


def solve_constrained_latent(
    observations: tuple[SolverObservation, ...],
    configuration: SolverConfiguration,
    *,
    initial: npt.NDArray[np.float64] | None = None,
    cancellation: CancellationContext | None = None,
) -> SolverOutcome:
    """Solve the constrained Huber objective by deterministic damped IRLS."""

    checkpoint(cancellation)
    if not observations:
        raise ValueError("at least one active observation is required")
    if initial is None:
        parameters = np.zeros(_PARAMETER_COUNT, dtype=_FLOAT)
    else:
        if initial.shape != (_PARAMETER_COUNT,) or not np.all(np.isfinite(initial)):
            raise ValueError("initial parameter vector is invalid")
        parameters = np.asarray(initial, dtype=_FLOAT).copy()
        parameters[1:] -= float(np.mean(parameters[1:]))

    trace: list[ObjectiveTraceRecord] = []
    converged = False
    maximum_candidate_update = math.inf
    for iteration in range(1, configuration.max_iterations + 1):
        checkpoint(cancellation)
        baseline = objective(parameters, observations, configuration)
        candidate = _irls_candidate(parameters, observations, configuration)
        maximum_candidate_update = float(np.max(np.abs(candidate - parameters)))
        candidate_objective = objective(candidate, observations, configuration)

        direction = candidate - parameters
        step = configuration.damping
        accepted = False
        accepted_parameters = parameters
        accepted_objective = baseline
        accepted_step = 0.0
        for _ in range(configuration.backtracking_steps):
            trial = parameters + step * direction
            trial[1:] -= float(np.mean(trial[1:]))
            trial_objective = objective(trial, observations, configuration)
            if trial_objective <= baseline + configuration.objective_increase_tolerance:
                accepted = step > 0.0
                accepted_parameters = trial
                accepted_objective = trial_objective
                accepted_step = step
                break
            step *= configuration.backtracking_factor

        parameters = accepted_parameters
        trace.append(
            ObjectiveTraceRecord(
                iteration=iteration,
                baseline_objective=baseline,
                candidate_objective=candidate_objective,
                accepted_objective=accepted_objective,
                damping=accepted_step,
                accepted=accepted,
            )
        )
        gradient_norm = float(
            np.max(np.abs(_projected_gradient(parameters, observations, configuration)))
        )
        accepted_update = accepted_step * maximum_candidate_update
        if (
            accepted
            and accepted_update <= configuration.tolerance
            and gradient_norm <= configuration.gradient_tolerance
        ):
            converged = True
            break

    final_objective = objective(parameters, observations, configuration)
    final_gradient_norm = float(
        np.max(np.abs(_projected_gradient(parameters, observations, configuration)))
    )
    axis_values = tuple(float(value) for value in parameters[1:])
    if len(axis_values) != _AXIS_COUNT:
        raise AssertionError("internal axis count changed")
    return SolverOutcome(
        intercept=float(parameters[0]),
        axis_values=(axis_values[0], axis_values[1], axis_values[2], axis_values[3]),
        converged=converged,
        iterations=len(trace),
        objective=final_objective,
        final_gradient_norm=final_gradient_norm,
        maximum_candidate_update=maximum_candidate_update,
        sum_to_zero_residual=math.fsum(axis_values),
        objective_trace=tuple(trace),
    )


__all__ = [
    "ObjectiveTraceRecord",
    "SolverConfiguration",
    "SolverObservation",
    "SolverOutcome",
    "objective",
    "solve_constrained_latent",
]

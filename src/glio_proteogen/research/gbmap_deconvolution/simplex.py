"""Convex reference-mixture inference with an adaptive unknown RNA channel.

The optimized weights are RNA-mixture weights, not cell-count fractions.  Known
lineages and the gene-resolved unknown channel share one simplex, so unknown
mass is never discarded and the known weights are never renormalized after the
fit.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .dm import (
    dirichlet_multinomial_per_count_nll,
    dm_probability_gradient,
)

_FLOAT: Final = np.float64
_PROBABILITY_TOLERANCE: Final = 1e-10


@dataclass(frozen=True, slots=True)
class SimplexSolverConfiguration:
    """Numerical constants for deterministic exponentiated-gradient inference."""

    max_iterations: int = 500
    max_backtracking_steps: int = 60
    initial_step: float = 1.0
    maximum_step: float = 64.0
    backtracking_factor: float = 0.5
    step_growth: float = 1.5
    armijo_fraction: float = 1e-4
    relative_objective_tolerance: float = 1e-10
    l1_step_tolerance: float = 1e-9
    kkt_tolerance: float = 1e-7
    objective_increase_tolerance: float = 1e-15
    simplex_floor: float = 1e-15
    active_weight_tolerance: float = 1e-10
    signature_condition_limit: float = 1e8
    minimum_signature_contrast: float = 1e-8

    def __post_init__(self) -> None:
        if self.max_iterations < 1 or self.max_backtracking_steps < 1:
            raise ValueError("solver iteration limits must be positive")
        positive = (
            self.initial_step,
            self.maximum_step,
            self.backtracking_factor,
            self.step_growth,
            self.relative_objective_tolerance,
            self.l1_step_tolerance,
            self.kkt_tolerance,
            self.simplex_floor,
            self.active_weight_tolerance,
            self.signature_condition_limit,
            self.minimum_signature_contrast,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("solver constants must be finite and positive")
        if not 0.0 < self.backtracking_factor < 1.0:
            raise ValueError("backtracking factor must be strictly between zero and one")
        if self.step_growth <= 1.0:
            raise ValueError("step growth must exceed one")
        if not 0.0 < self.armijo_fraction < 1.0:
            raise ValueError("Armijo fraction must be strictly between zero and one")
        if self.simplex_floor * 3.0 >= 1.0:
            raise ValueError("simplex floor is too large")
        if (
            not math.isfinite(self.objective_increase_tolerance)
            or self.objective_increase_tolerance < 0.0
        ):
            raise ValueError("objective increase tolerance must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class SimplexTraceRecord:
    iteration: int
    objective: float
    accepted_step: float
    backtracking_steps: int
    relative_objective_change: float
    l1_step: float
    kkt_residual: float
    unknown_mass: float


@dataclass(frozen=True, slots=True)
class ReferenceMixtureSolution:
    """One deterministic convex fit, retaining gene-resolved unknown mass."""

    known_rna_weights: npt.NDArray[np.float64]
    unknown_gene_mass: npt.NDArray[np.float64]
    fitted_probabilities: npt.NDArray[np.float64]
    unknown_mass: float
    initial_objective: float
    objective: float
    converged: bool
    iterations: int
    kkt_residual: float
    signature_condition_number: float
    trace: tuple[SimplexTraceRecord, ...]

    def __post_init__(self) -> None:
        for name in ("known_rna_weights", "unknown_gene_mass", "fitted_probabilities"):
            value = np.array(getattr(self, name), dtype=_FLOAT, copy=True)
            if value.ndim != 1 or not np.all(np.isfinite(value)) or np.any(value < 0.0):
                raise ValueError(f"{name} must be a finite non-negative vector")
            value.flags.writeable = False
            object.__setattr__(self, name, value)
        if self.known_rna_weights.size < 1:
            raise ValueError("solution must contain at least one known lineage")
        if self.unknown_gene_mass.size != self.fitted_probabilities.size:
            raise ValueError("unknown weights and fitted probabilities must share a gene axis")
        if not math.isclose(
            math.fsum(float(value) for value in self.known_rna_weights)
            + math.fsum(float(value) for value in self.unknown_gene_mass),
            1.0,
            rel_tol=0.0,
            abs_tol=2e-12,
        ):
            raise ValueError("known and unknown weights must share one simplex")
        if not math.isclose(
            self.unknown_mass,
            math.fsum(float(value) for value in self.unknown_gene_mass),
            rel_tol=0.0,
            abs_tol=2e-12,
        ):
            raise ValueError("reported unknown mass does not match its gene-resolved weights")
        if not math.isclose(
            math.fsum(float(value) for value in self.fitted_probabilities),
            1.0,
            rel_tol=0.0,
            abs_tol=2e-12,
        ):
            raise ValueError("fitted gene probabilities must sum to one")
        scalar_values = (
            self.unknown_mass,
            self.initial_objective,
            self.objective,
            self.kkt_residual,
            self.signature_condition_number,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in scalar_values):
            raise ValueError("solution diagnostics must be finite and non-negative")
        if self.iterations < 0 or self.iterations != len(self.trace):
            raise ValueError("solution iteration count is inconsistent with its trace")
        if tuple(item.iteration for item in self.trace) != tuple(range(1, self.iterations + 1)):
            raise ValueError("solution trace iterations must be contiguous and ordered")


def _probability_vector(values: npt.ArrayLike, *, name: str) -> npt.NDArray[np.float64]:
    source = np.asarray(values)
    if source.dtype.kind not in "fiu" or source.dtype.kind == "b":
        raise TypeError(f"{name} must be a numeric probability vector")
    vector = np.asarray(source, dtype=_FLOAT)
    if vector.ndim != 1 or vector.size < 2:
        raise ValueError(f"{name} must be a one-dimensional vector with at least two entries")
    if not np.all(np.isfinite(vector)) or np.any(vector <= 0.0):
        raise ValueError(f"{name} must contain finite, strictly positive probabilities")
    if not math.isclose(
        math.fsum(float(value) for value in vector),
        1.0,
        rel_tol=0.0,
        abs_tol=_PROBABILITY_TOLERANCE,
    ):
        raise ValueError(f"{name} must sum to one")
    return np.array(vector, dtype=_FLOAT, copy=True)


def _signature_matrix(values: npt.ArrayLike) -> npt.NDArray[np.float64]:
    source = np.asarray(values)
    if source.dtype.kind not in "fiu" or source.dtype.kind == "b":
        raise TypeError("reference signatures must be numeric")
    signatures = np.asarray(source, dtype=_FLOAT)
    if signatures.ndim != 2 or min(signatures.shape) < 1 or signatures.shape[0] < 2:
        raise ValueError("reference signatures must have shape (genes, lineages)")
    if not np.all(np.isfinite(signatures)) or np.any(signatures <= 0.0):
        raise ValueError("reference signatures must be finite and strictly positive")
    for column in range(signatures.shape[1]):
        total = math.fsum(float(value) for value in signatures[:, column])
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=_PROBABILITY_TOLERANCE):
            raise ValueError("every reference signature must sum to one")
    return np.array(signatures, dtype=_FLOAT, copy=True, order="C")


def _nonnegative_scalar(value: float, *, name: str) -> float:
    converted = float(value)
    if not math.isfinite(converted) or converted < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return converted


def reference_signature_condition_number(signatures: npt.ArrayLike) -> float:
    """Return the simplex-tangent condition number of known signatures."""

    matrix = _signature_matrix(signatures)
    if matrix.shape[1] == 1:
        return 1.0
    contrasts = matrix[:, :-1] - matrix[:, [-1]]
    singular_values = np.linalg.svd(contrasts, compute_uv=False)
    if singular_values.size == 0:
        return math.inf
    largest = float(singular_values[0])
    smallest = float(singular_values[-1])
    if smallest == 0.0:
        return math.inf
    return largest / smallest


def _validate_weights(
    signatures: npt.NDArray[np.float64],
    known_weights: npt.ArrayLike,
    unknown_gene_mass: npt.ArrayLike,
    *,
    gradient: bool,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    known = np.asarray(known_weights, dtype=_FLOAT)
    unknown = np.asarray(unknown_gene_mass, dtype=_FLOAT)
    if known.shape != (signatures.shape[1],) or unknown.shape != (signatures.shape[0],):
        raise ValueError("mixture weights do not match the reference dimensions")
    if not np.all(np.isfinite(known)) or not np.all(np.isfinite(unknown)):
        raise ValueError("mixture weights must be finite")
    if np.any(known < 0.0) or np.any(unknown < 0.0):
        raise ValueError("mixture weights must be non-negative")
    if gradient and np.any(unknown <= 0.0):
        raise ValueError("gradient evaluation requires strictly positive unknown weights")
    total = math.fsum(float(value) for value in known) + math.fsum(
        float(value) for value in unknown
    )
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=_PROBABILITY_TOLERANCE):
        raise ValueError("known and unknown weights must share one simplex")
    return np.array(known, dtype=_FLOAT, copy=True), np.array(unknown, dtype=_FLOAT, copy=True)


def reference_mixture_objective(
    counts: npt.ArrayLike,
    signatures: npt.ArrayLike,
    background: npt.ArrayLike,
    known_weights: npt.ArrayLike,
    unknown_gene_mass: npt.ArrayLike,
    *,
    concentration: float,
    lambda_mass: float,
    lambda_shape: float,
) -> float:
    """Evaluate the exact convex DM plus adaptive-unknown objective."""

    matrix = _signature_matrix(signatures)
    base = _probability_vector(background, name="unknown background")
    if base.shape[0] != matrix.shape[0]:
        raise ValueError("unknown background does not match the reference gene axis")
    known, unknown = _validate_weights(
        matrix,
        known_weights,
        unknown_gene_mass,
        gradient=False,
    )
    mass_penalty = _nonnegative_scalar(lambda_mass, name="unknown-mass penalty")
    shape_penalty = _nonnegative_scalar(lambda_shape, name="unknown-shape penalty")
    return _objective_prepared(
        counts,
        matrix,
        base,
        known,
        unknown,
        concentration=concentration,
        lambda_mass=mass_penalty,
        lambda_shape=shape_penalty,
    )


def _objective_prepared(
    counts: npt.ArrayLike,
    matrix: npt.NDArray[np.float64],
    base: npt.NDArray[np.float64],
    known: npt.NDArray[np.float64],
    unknown: npt.NDArray[np.float64],
    *,
    concentration: float,
    lambda_mass: float,
    lambda_shape: float,
) -> float:
    probabilities = matrix @ known + unknown
    nll = dirichlet_multinomial_per_count_nll(counts, probabilities, concentration)
    unknown_total = math.fsum(float(value) for value in unknown)
    shape = 0.0
    if unknown_total > 0.0:
        shape = math.fsum(
            float(value) * math.log(float(value) / (unknown_total * float(base[index])))
            for index, value in enumerate(unknown)
            if value > 0.0
        )
    objective = nll + lambda_mass * unknown_total + lambda_shape * shape
    if not math.isfinite(objective):
        raise FloatingPointError("reference-mixture objective became non-finite")
    return objective


def reference_mixture_gradient(
    counts: npt.ArrayLike,
    signatures: npt.ArrayLike,
    background: npt.ArrayLike,
    known_weights: npt.ArrayLike,
    unknown_gene_mass: npt.ArrayLike,
    *,
    concentration: float,
    lambda_mass: float,
    lambda_shape: float,
) -> npt.NDArray[np.float64]:
    """Return the gradient on the combined known-plus-unknown simplex."""

    matrix = _signature_matrix(signatures)
    base = _probability_vector(background, name="unknown background")
    if base.shape[0] != matrix.shape[0]:
        raise ValueError("unknown background does not match the reference gene axis")
    known, unknown = _validate_weights(
        matrix,
        known_weights,
        unknown_gene_mass,
        gradient=True,
    )
    mass_penalty = _nonnegative_scalar(lambda_mass, name="unknown-mass penalty")
    shape_penalty = _nonnegative_scalar(lambda_shape, name="unknown-shape penalty")
    return _gradient_prepared(
        counts,
        matrix,
        base,
        known,
        unknown,
        concentration=concentration,
        lambda_mass=mass_penalty,
        lambda_shape=shape_penalty,
    )


def _gradient_prepared(
    counts: npt.ArrayLike,
    matrix: npt.NDArray[np.float64],
    base: npt.NDArray[np.float64],
    known: npt.NDArray[np.float64],
    unknown: npt.NDArray[np.float64],
    *,
    concentration: float,
    lambda_mass: float,
    lambda_shape: float,
) -> npt.NDArray[np.float64]:
    probabilities = matrix @ known + unknown
    likelihood_gradient = dm_probability_gradient(counts, probabilities, concentration)
    unknown_total = math.fsum(float(value) for value in unknown)
    if unknown_total <= 0.0:
        raise ValueError("gradient evaluation requires positive total unknown mass")
    known_gradient = matrix.T @ likelihood_gradient
    unknown_gradient = likelihood_gradient + lambda_mass
    unknown_gradient += lambda_shape * np.log(unknown / (unknown_total * base))
    combined = np.concatenate((known_gradient, unknown_gradient)).astype(_FLOAT, copy=False)
    if not np.all(np.isfinite(combined)):
        raise FloatingPointError("reference-mixture gradient became non-finite")
    return combined


def _kkt_residual(
    weights: npt.NDArray[np.float64],
    gradient: npt.NDArray[np.float64],
    active_tolerance: float,
) -> float:
    active = weights > active_tolerance
    if not np.any(active):
        return math.inf
    multiplier = float(np.mean(gradient[active]))
    active_residual = float(np.max(np.abs(gradient[active] - multiplier)))
    inactive_residual = 0.0
    if np.any(~active):
        inactive_residual = float(np.max(np.maximum(multiplier - gradient[~active], 0.0)))
    return max(active_residual, inactive_residual)


def _floored_simplex(values: npt.NDArray[np.float64], floor: float) -> npt.NDArray[np.float64]:
    size = int(values.size)
    floor_mass = floor * size
    if floor_mass >= 1.0:
        raise ValueError("simplex floor exceeds the available mass")
    normalized = values / float(np.sum(values, dtype=_FLOAT))
    return floor + (1.0 - floor_mass) * normalized


def _initial_weights(
    lineage_count: int,
    background: npt.NDArray[np.float64],
    initial_unknown_mass: float,
    floor: float,
) -> npt.NDArray[np.float64]:
    unknown_mass = float(initial_unknown_mass)
    if not math.isfinite(unknown_mass) or not 0.0 < unknown_mass < 1.0:
        raise ValueError("initial unknown mass must lie strictly between zero and one")
    known = np.full(lineage_count, (1.0 - unknown_mass) / lineage_count, dtype=_FLOAT)
    unknown = unknown_mass * background
    return _floored_simplex(np.concatenate((known, unknown)), floor)


@dataclass(frozen=True, slots=True)
class _LineSearchResult:
    weights: npt.NDArray[np.float64]
    objective: float
    step: float
    backtracking_steps: int


def _line_search(
    weights: npt.NDArray[np.float64],
    gradient: npt.NDArray[np.float64],
    objective: float,
    step: float,
    evaluate: Callable[[npt.NDArray[np.float64]], float],
    *,
    config: SimplexSolverConfiguration,
) -> _LineSearchResult | None:
    centered = gradient - float(weights @ gradient)
    candidate_step = step
    for attempt in range(config.max_backtracking_steps):
        log_candidate = np.log(weights) - candidate_step * centered
        log_candidate -= float(np.max(log_candidate))
        raw_candidate = np.exp(np.maximum(log_candidate, -745.0))
        candidate = _floored_simplex(raw_candidate, config.simplex_floor)
        directional = float(gradient @ (candidate - weights))
        candidate_objective = evaluate(candidate)
        armijo_bound = objective + config.armijo_fraction * directional
        if (
            directional <= 0.0
            and candidate_objective <= armijo_bound + config.objective_increase_tolerance
            and candidate_objective <= objective + config.objective_increase_tolerance
        ):
            return _LineSearchResult(
                weights=candidate,
                objective=candidate_objective,
                step=candidate_step,
                backtracking_steps=attempt,
            )
        candidate_step *= config.backtracking_factor
    return None


def solve_reference_mixture(
    counts: npt.ArrayLike,
    signatures: npt.ArrayLike,
    background: npt.ArrayLike,
    *,
    concentration: float,
    lambda_mass: float,
    lambda_shape: float,
    configuration: SimplexSolverConfiguration | None = None,
    initial_unknown_mass: float = 0.05,
    cancellation: CancellationContext | None = None,
) -> ReferenceMixtureSolution:
    """Fit known lineage RNA weights and explicit unexplained gene mass."""

    config = configuration or SimplexSolverConfiguration()
    matrix = _signature_matrix(signatures)
    base = _probability_vector(background, name="unknown background")
    if base.shape[0] != matrix.shape[0]:
        raise ValueError("unknown background does not match the reference gene axis")
    condition = reference_signature_condition_number(matrix)
    if matrix.shape[1] > 1:
        contrasts = matrix[:, :-1] - matrix[:, [-1]]
        smallest_contrast = float(np.linalg.svd(contrasts, compute_uv=False)[-1])
        if (
            not math.isfinite(condition)
            or condition > config.signature_condition_limit
            or smallest_contrast < config.minimum_signature_contrast
        ):
            raise ValueError("reference signatures are not identifiable on the simplex")

    weights = _initial_weights(
        matrix.shape[1],
        base,
        initial_unknown_mass,
        config.simplex_floor,
    )
    known_count = matrix.shape[1]

    def evaluate(candidate: npt.NDArray[np.float64]) -> float:
        return _objective_prepared(
            counts,
            matrix,
            base,
            candidate[:known_count],
            candidate[known_count:],
            concentration=concentration,
            lambda_mass=lambda_mass,
            lambda_shape=lambda_shape,
        )

    def derivative(candidate: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        return _gradient_prepared(
            counts,
            matrix,
            base,
            candidate[:known_count],
            candidate[known_count:],
            concentration=concentration,
            lambda_mass=lambda_mass,
            lambda_shape=lambda_shape,
        )

    checkpoint(cancellation)
    objective = evaluate(weights)
    initial_objective = objective
    gradient = derivative(weights)
    kkt = _kkt_residual(weights, gradient, config.active_weight_tolerance)
    step = min(config.initial_step, config.maximum_step)
    trace: list[SimplexTraceRecord] = []
    converged = False

    for iteration in range(1, config.max_iterations + 1):
        checkpoint(cancellation)
        line_search = _line_search(
            weights,
            gradient,
            objective,
            step,
            evaluate,
            config=config,
        )
        if line_search is None:
            break

        previous_objective = objective
        l1_step = math.fsum(float(value) for value in np.abs(line_search.weights - weights))
        weights = line_search.weights
        objective = line_search.objective
        gradient = derivative(weights)
        kkt = _kkt_residual(weights, gradient, config.active_weight_tolerance)
        relative_change = abs(previous_objective - objective) / max(1.0, abs(previous_objective))
        unknown_mass = math.fsum(float(value) for value in weights[known_count:])
        trace.append(
            SimplexTraceRecord(
                iteration=iteration,
                objective=objective,
                accepted_step=line_search.step,
                backtracking_steps=line_search.backtracking_steps,
                relative_objective_change=relative_change,
                l1_step=l1_step,
                kkt_residual=kkt,
                unknown_mass=unknown_mass,
            )
        )
        if (
            relative_change <= config.relative_objective_tolerance
            and l1_step <= config.l1_step_tolerance
            and kkt <= config.kkt_tolerance
        ):
            converged = True
            break
        step = min(line_search.step * config.step_growth, config.maximum_step)

    known = np.array(weights[:known_count], dtype=_FLOAT, copy=True)
    unknown = np.array(weights[known_count:], dtype=_FLOAT, copy=True)
    fitted = matrix @ known + unknown
    return ReferenceMixtureSolution(
        known_rna_weights=known,
        unknown_gene_mass=unknown,
        fitted_probabilities=fitted,
        unknown_mass=math.fsum(float(value) for value in unknown),
        initial_objective=initial_objective,
        objective=objective,
        converged=converged,
        iterations=len(trace),
        kkt_residual=kkt,
        signature_condition_number=condition,
        trace=tuple(trace),
    )


def verify_objective_trace(
    solution: ReferenceMixtureSolution,
    *,
    tolerance: float = 1e-10,
) -> bool:
    """Verify monotonicity and final-diagnostic binding of a solver trace."""

    allowed = float(tolerance)
    if not math.isfinite(allowed) or allowed < 0.0 or not solution.trace:
        return False
    previous = solution.initial_objective
    for record in solution.trace:
        values = (
            record.objective,
            record.accepted_step,
            record.relative_objective_change,
            record.l1_step,
            record.kkt_residual,
            record.unknown_mass,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            return False
        if record.objective > previous + allowed:
            return False
        previous = record.objective
    final = solution.trace[-1]
    return (
        math.isclose(solution.objective, final.objective, rel_tol=0.0, abs_tol=allowed)
        and math.isclose(solution.kkt_residual, final.kkt_residual, rel_tol=0.0, abs_tol=allowed)
        and math.isclose(solution.unknown_mass, final.unknown_mass, rel_tol=0.0, abs_tol=allowed)
    )


__all__ = [
    "ReferenceMixtureSolution",
    "SimplexSolverConfiguration",
    "SimplexTraceRecord",
    "reference_mixture_gradient",
    "reference_mixture_objective",
    "reference_signature_condition_number",
    "solve_reference_mixture",
    "verify_objective_trace",
]

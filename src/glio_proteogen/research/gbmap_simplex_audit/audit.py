"""Request-bound endpoint equations without solving or changing old admission.

The unchanged legacy scalar trace is checked separately. Its intermediate
iterates are unavailable, so this audit cannot authenticate their equations.
All returned values are private per-fit scalars, not a privacy guarantee.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict
from importlib.resources import files
from numbers import Integral, Real
from typing import Literal

import numpy as np
import numpy.typing as npt

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbmap_deconvolution import simplex
from glio_proteogen.research.gbmap_deconvolution.dm import dirichlet_multinomial_per_count_nll
from glio_proteogen.research.gbmap_deconvolution.errors import GbmapNumericalError
from glio_proteogen.research.gbmap_deconvolution.simplex import (
    ReferenceMixtureSolution,
    SimplexSolverConfiguration,
    SimplexTraceRecord,
)
from glio_proteogen.research.gbmap_mixture_benchmark import MixturePointPolicy

from .contracts import (
    DIAGNOSTIC_TOLERANCE,
    ENDPOINT_TOLERANCE,
    SOLVER_CONFIGURATION_DIGEST,
    SimplexAuditError,
    SimplexEndpointAudit,
)

FloatArray = npt.NDArray[np.float64]
_NUMERIC_FAILURES = (GbmapNumericalError, FloatingPointError, OverflowError, ValueError)


def _method_digest() -> str:
    """Bind normalized code bytes and constants, never numerical request bytes."""
    packages = (
        ("gbmap_simplex_audit", ("__init__.py", "contracts.py", "audit.py")),
        ("gbmap_deconvolution", ("simplex.py", "dm.py", "numerics.py", "errors.py")),
        ("gbmap_mixture_benchmark", ("contracts.py",)),
    )
    bindings: dict[str, str] = {}
    for package, names in packages:
        root = files(f"glio_proteogen.research.{package}")
        for name in names:
            content = root.joinpath(name).read_bytes().replace(b"\r\n", b"\n")
            bindings[f"{package}/{name}"] = f"sha256:{hashlib.sha256(content).hexdigest()}"
    return sha256_digest(
        {
            "audit_version": "gbmap-simplex-endpoint-audit/1.0.0",
            "code": bindings,
            "configuration": asdict(SimplexSolverConfiguration()),
            "endpoint_tolerance": ENDPOINT_TOLERANCE,
            "diagnostic_tolerance": DIAGNOSTIC_TOLERANCE,
        }
    )


def _numeric_array(values: npt.ArrayLike, *, dimensions: int) -> FloatArray:
    if np.ma.isMaskedArray(values):
        raise SimplexAuditError("invalid simplex audit numeric domain")
    raw = np.asarray(values, dtype=object)
    if raw.ndim != dimensions or any(not _finite_real(value) for value in raw.flat):
        raise SimplexAuditError("invalid simplex audit numeric domain")
    array = np.array(raw, dtype=np.float64, copy=True)
    if not np.all(np.isfinite(array)):
        raise SimplexAuditError("invalid simplex audit numeric domain")
    return array


def _finite_real(value: object) -> bool:
    return (
        not isinstance(value, (bool, np.bool_))
        and isinstance(value, Real)
        and math.isfinite(float(value))
    )


def _request(
    counts: npt.ArrayLike,
    signatures: npt.ArrayLike,
    background: npt.ArrayLike,
) -> tuple[npt.NDArray[np.int64], int, FloatArray, FloatArray]:
    if np.ma.isMaskedArray(counts):
        raise SimplexAuditError("invalid simplex audit count domain")
    raw = np.asarray(counts, dtype=object)
    if raw.ndim != 1 or raw.size < 2:
        raise SimplexAuditError("invalid simplex audit request")
    converted: list[int] = []
    for value in raw:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
            raise SimplexAuditError("invalid simplex audit count domain")
        number = int(value)
        if not 0 <= number <= np.iinfo(np.int64).max:
            raise SimplexAuditError("invalid simplex audit count domain")
        converted.append(number)
    depth = sum(converted)
    if not 0 < depth <= np.iinfo(np.int64).max:
        raise SimplexAuditError("invalid simplex audit count depth")
    matrix = _numeric_array(signatures, dimensions=2)
    base = _numeric_array(background, dimensions=1)
    if (
        matrix.shape[0] != raw.size
        or matrix.shape[1] < 1
        or base.shape != (raw.size,)
        or np.any(matrix <= 0.0)
        or np.any(base <= 0.0)
        or any(
            not math.isclose(
                math.fsum(float(v) for v in matrix[:, j]), 1.0, rel_tol=0.0, abs_tol=1e-10
            )
            for j in range(matrix.shape[1])
        )
        or not math.isclose(math.fsum(float(v) for v in base), 1.0, rel_tol=0.0, abs_tol=1e-10)
    ):
        raise SimplexAuditError("invalid simplex audit probability domain")
    return np.asarray(converted, dtype=np.int64), depth, matrix, base


def _endpoint(
    solution: ReferenceMixtureSolution, features: int, labels: int
) -> tuple[FloatArray, FloatArray, FloatArray]:
    if type(solution) is not ReferenceMixtureSolution:
        raise SimplexAuditError("invalid simplex audit solution type")
    known = _numeric_array(solution.known_rna_weights, dimensions=1)
    unknown = _numeric_array(solution.unknown_gene_mass, dimensions=1)
    fitted = _numeric_array(solution.fitted_probabilities, dimensions=1)
    if (
        known.shape != (labels,)
        or unknown.shape != (features,)
        or fitted.shape != (features,)
        or np.any(known < 0.0)
        or np.any(unknown < 0.0)
        or np.any(fitted < 0.0)
        or type(solution.converged) is not bool
        or type(solution.iterations) is not int
        or solution.iterations < 0
        or type(solution.trace) is not tuple
        or solution.iterations != len(solution.trace)
        or any(type(record) is not SimplexTraceRecord for record in solution.trace)
        or tuple(record.iteration for record in solution.trace)
        != tuple(range(1, solution.iterations + 1))
    ):
        raise SimplexAuditError("invalid simplex audit solution structure")
    scalars = (
        solution.unknown_mass,
        solution.initial_objective,
        solution.objective,
        solution.kkt_residual,
        solution.signature_condition_number,
    )
    if any(not _finite_real(v) or v < 0.0 for v in scalars):
        raise SimplexAuditError("invalid simplex audit solution scalars")
    # The original solution constructor already requires these structural
    # simplexes. Request-equation mismatches remain diagnostics, not rejection.
    if (
        abs(math.fsum(float(v) for v in np.concatenate((known, unknown))) - 1.0)
        > ENDPOINT_TOLERANCE
        or abs(math.fsum(float(v) for v in fitted) - 1.0) > ENDPOINT_TOLERANCE
    ):
        raise SimplexAuditError("invalid simplex audit solution simplex")
    return known, unknown, fitted


def _objective_terms(
    counts: npt.NDArray[np.int64],
    matrix: FloatArray,
    base: FloatArray,
    known: FloatArray,
    unknown: FloatArray,
    *,
    policy: MixturePointPolicy,
) -> tuple[float, float, float, float, float]:
    nll = dirichlet_multinomial_per_count_nll(
        counts, matrix @ known + unknown, policy.concentration
    )
    total = math.fsum(float(v) for v in unknown)
    shape = (
        math.fsum(
            float(value) * math.log(float(value) / (total * float(base[index])))
            for index, value in enumerate(unknown)
            if value > 0.0
        )
        if total > 0.0
        else 0.0
    )
    mass_penalty = policy.lambda_mass * total
    shape_penalty = policy.lambda_shape * shape
    objective = nll + mass_penalty + shape_penalty
    terms = (nll, mass_penalty, shape, shape_penalty, objective)
    if any(not math.isfinite(value) for value in terms):
        raise FloatingPointError("unavailable simplex audit objective")
    return terms


def audit_simplex_solution(
    counts: npt.ArrayLike,
    signatures: npt.ArrayLike,
    background: npt.ArrayLike,
    policy: MixturePointPolicy,
    solution: ReferenceMixtureSolution,
) -> SimplexEndpointAudit:
    """Recompute request-bound endpoints without training, solving or admitting.

    The raw Frank-Wolfe expression is ``g@w-min(g)``; the stable expression
    is ``sum(w*(g-min(g)))``. Their difference includes simplex-closure and
    float64 reduction error. Neither is an interval-certified objective bound.
    Unknown boundary coordinates make the unchanged gradient unavailable.
    """
    if type(policy) is not MixturePointPolicy:
        raise SimplexAuditError("invalid simplex audit policy")
    try:
        policy = MixturePointPolicy.model_validate(policy)
        count_values, depth, matrix, base = _request(counts, signatures, background)
        known, unknown, fitted = _endpoint(solution, matrix.shape[0], matrix.shape[1])
        return _audit(
            count_values,
            depth,
            matrix,
            base,
            policy,
            solution=solution,
            known=known,
            unknown=unknown,
            fitted=fitted,
        )
    except SimplexAuditError:
        raise
    except (TypeError, ValueError, OverflowError, AttributeError, IndexError):
        raise SimplexAuditError("invalid simplex audit request or solution") from None


def _audit(  # noqa: PLR0915 - explicit scalar availability and unchanged gate reconstruction.
    counts: npt.NDArray[np.int64],
    depth: int,
    matrix: FloatArray,
    base: FloatArray,
    policy: MixturePointPolicy,
    *,
    solution: ReferenceMixtureSolution,
    known: FloatArray,
    unknown: FloatArray,
    fitted: FloatArray,
) -> SimplexEndpointAudit:
    config = SimplexSolverConfiguration()
    weights = np.concatenate((known, unknown))
    reconstructed = matrix @ known + unknown
    weight_sum = math.fsum(float(v) for v in weights)
    recomputed_unknown = math.fsum(float(v) for v in unknown)
    unknown_error = abs(float(solution.unknown_mass) - recomputed_unknown)
    fitted_error = float(np.max(np.abs(fitted - reconstructed)))
    initial = simplex._initial_weights(
        matrix.shape[1], base, policy.initial_unknown_mass, config.simplex_floor
    )
    initial_error = float(np.max(np.abs(weights - initial)))

    terms: tuple[float, float, float, float, float] | None = None
    initial_objective: float | None = None
    with np.errstate(over="raise", divide="raise", invalid="raise", under="ignore"):
        try:
            terms = _objective_terms(counts, matrix, base, known, unknown, policy=policy)
        except (*_NUMERIC_FAILURES, ZeroDivisionError):
            pass
        try:
            initial_objective = _objective_terms(
                counts,
                matrix,
                base,
                initial[: matrix.shape[1]],
                initial[matrix.shape[1] :],
                policy=policy,
            )[-1]
        except (*_NUMERIC_FAILURES, ZeroDivisionError):
            pass
    objective_error = abs(float(solution.objective) - terms[-1]) if terms is not None else None
    initial_objective_error = (
        abs(float(solution.initial_objective) - initial_objective)
        if initial_objective is not None
        else None
    )

    gradient_status: Literal["available", "boundary_unknown_zero", "numerical_failure"] = (
        "boundary_unknown_zero" if np.any(unknown == 0.0) else "numerical_failure"
    )
    kkt: float | None = None
    raw_gap: float | None = None
    stable_gap: float | None = None
    if gradient_status != "boundary_unknown_zero":
        try:
            with np.errstate(over="raise", divide="raise", invalid="raise", under="ignore"):
                gradient = simplex.reference_mixture_gradient(
                    counts,
                    matrix,
                    base,
                    known,
                    unknown,
                    concentration=policy.concentration,
                    lambda_mass=policy.lambda_mass,
                    lambda_shape=policy.lambda_shape,
                )
                recomputed_kkt = simplex._kkt_residual(
                    weights, gradient, config.active_weight_tolerance
                )
                minimum = float(np.min(gradient))
                raw = float(gradient @ weights) - minimum
                stable = math.fsum(
                    float(w) * (float(g) - minimum) for w, g in zip(weights, gradient, strict=True)
                )
                if not all(math.isfinite(value) for value in (recomputed_kkt, raw, stable)):
                    raise FloatingPointError("unavailable simplex audit gradient")
                kkt, raw_gap, stable_gap = recomputed_kkt, raw, stable
                gradient_status = "available"
        except _NUMERIC_FAILURES:
            pass
    kkt_error = abs(float(solution.kkt_residual) - kkt) if kkt is not None else None

    condition_status: Literal["available", "numerical_failure"] = "numerical_failure"
    condition: float | None = None
    smallest: float | None = None
    conditioning_passed = False
    try:
        condition_value = simplex.reference_signature_condition_number(matrix)
        smallest = (
            float(np.linalg.svd(matrix[:, :-1] - matrix[:, [-1]], compute_uv=False)[-1])
            if matrix.shape[1] > 1
            else None
        )
        condition = condition_value if math.isfinite(condition_value) else None
        conditioning_passed = matrix.shape[1] == 1 or (
            condition is not None
            and condition <= config.signature_condition_limit
            and smallest is not None
            and smallest >= config.minimum_signature_contrast
        )
        condition_status = "available"
    except (np.linalg.LinAlgError, FloatingPointError, OverflowError, ValueError):
        condition, smallest = None, None
    condition_error = (
        abs(float(solution.signature_condition_number) - condition)
        if condition is not None
        else None
    )
    trace_consistent = simplex.verify_objective_trace(solution)
    legacy_status: Literal[
        "signature_conditioning_rejected", "solver_trace_invalid", "solver_not_converged", "scored"
    ] = (
        "signature_conditioning_rejected"
        if not conditioning_passed
        else "solver_trace_invalid"
        if not trace_consistent
        else "solver_not_converged"
        if not solution.converged or solution.kkt_residual > config.kkt_tolerance
        else "scored"
    )
    stationary = kkt <= config.kkt_tolerance if kkt is not None else None
    return SimplexEndpointAudit(
        policy=policy,
        method_digest=_method_digest(),
        solver_configuration_digest=SOLVER_CONFIGURATION_DIGEST,
        feature_count=matrix.shape[0],
        known_label_count=matrix.shape[1],
        count_depth=depth,
        iterations=solution.iterations,
        reported_converged=solution.converged,
        reported_initial_objective=float(solution.initial_objective),
        reported_objective=float(solution.objective),
        reported_unknown_mass=float(solution.unknown_mass),
        reported_kkt_residual=float(solution.kkt_residual),
        reported_signature_condition_number=float(solution.signature_condition_number),
        legacy_trace_consistent=trace_consistent,
        legacy_benchmark_status=legacy_status,
        weight_simplex_sum=weight_sum,
        weight_simplex_absolute_error=abs(weight_sum - 1.0),
        fitted_probability_simplex_absolute_error=abs(math.fsum(float(v) for v in fitted) - 1.0),
        reconstructed_probability_simplex_absolute_error=abs(
            math.fsum(float(v) for v in reconstructed) - 1.0
        ),
        fitted_probability_max_absolute_error=fitted_error,
        reconstructed_probabilities_match=fitted_error <= ENDPOINT_TOLERANCE,
        recomputed_unknown_mass=recomputed_unknown,
        unknown_mass_absolute_error=unknown_error,
        unknown_mass_matches=unknown_error <= ENDPOINT_TOLERANCE,
        objective_status="available" if terms is not None else "numerical_failure",
        recomputed_nll=terms[0] if terms is not None else None,
        recomputed_mass_penalty=terms[1] if terms is not None else None,
        recomputed_shape_divergence=terms[2] if terms is not None else None,
        recomputed_shape_penalty=terms[3] if terms is not None else None,
        recomputed_objective=terms[4] if terms is not None else None,
        objective_absolute_error=objective_error,
        objective_matches=objective_error <= DIAGNOSTIC_TOLERANCE
        if objective_error is not None
        else None,
        initial_objective_status="available"
        if initial_objective is not None
        else "numerical_failure",
        recomputed_initial_objective=initial_objective,
        initial_objective_absolute_error=initial_objective_error,
        initial_objective_matches=initial_objective_error <= DIAGNOSTIC_TOLERANCE
        if initial_objective_error is not None
        else None,
        gradient_status=gradient_status,
        recomputed_kkt_residual=kkt,
        kkt_absolute_error=kkt_error,
        kkt_matches=kkt_error <= DIAGNOSTIC_TOLERANCE if kkt_error is not None else None,
        default_stationary=stationary,
        raw_frank_wolfe_gap=raw_gap,
        stable_frank_wolfe_gap=stable_gap,
        frank_wolfe_gap_difference=raw_gap - stable_gap
        if raw_gap is not None and stable_gap is not None
        else None,
        conditioning_status=condition_status,
        recomputed_signature_condition_number=condition,
        smallest_signature_contrast=smallest,
        default_conditioning_passed=conditioning_passed,
        condition_number_absolute_error=condition_error,
        condition_number_matches=condition_error <= DIAGNOSTIC_TOLERANCE
        if condition_error is not None
        else False,
        initial_endpoint_max_absolute_error=initial_error,
        endpoint_matches_initial=initial_error <= ENDPOINT_TOLERANCE,
        zero_step_endpoint_matches_initial=initial_error <= ENDPOINT_TOLERANCE
        if solution.iterations == 0
        else None,
        zero_step_stationary=stationary if solution.iterations == 0 else None,
    )

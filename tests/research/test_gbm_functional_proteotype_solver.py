"""Independent numerical oracles for the functional-proteotype latent solver."""

from __future__ import annotations

import math

import numpy as np
import pytest

from glio_proteogen.research.gbm_functional_proteotype.solver import (
    SolverConfiguration,
    SolverObservation,
    solve_constrained_latent,
)


def _configuration(**updates: float) -> SolverConfiguration:
    values: dict[str, float] = {
        "huber_delta": 1.345,
        "standard_error_floor": 0.25,
        "axis_ridge": 0.05,
        "intercept_ridge": 0.01,
        "damping": 0.8,
        "tolerance": 1e-9,
        "gradient_tolerance": 1e-8,
        "max_iterations": 200,
        "backtracking_factor": 0.5,
        "backtracking_steps": 24,
        "objective_increase_tolerance": 1e-12,
    }
    values.update(updates)
    return SolverConfiguration(**values)  # type: ignore[arg-type]


def _observation(  # noqa: PLR0913
    axis: int,
    value: float,
    *,
    state: str = "observed",
    loading: float = 1.0,
    error: float = 0.5,
    quality: float = 1.0,
) -> SolverObservation:
    return SolverObservation(
        axis_index=axis,
        source_loading=loading,
        state=state,  # type: ignore[arg-type]
        value=value,
        standard_error=error,
        quality_weight=quality,
    )


def test_quadratic_regime_matches_independent_constrained_ridge_oracle() -> None:
    configuration = _configuration(
        huber_delta=1_000.0,
        standard_error_floor=0.2,
        axis_ridge=0.2,
        intercept_ridge=0.1,
        damping=1.0,
    )
    observations = tuple(
        _observation(
            axis,
            value,
            loading=loading,
            error=error,
            quality=quality,
        )
        for axis, value, loading, error, quality in (
            (0, 1.8, 1.2, 0.4, 0.9),
            (0, 1.2, 0.8, 0.6, 1.0),
            (1, -0.9, 1.1, 0.5, 0.8),
            (1, -0.4, 0.9, 0.7, 1.0),
            (2, 0.7, 1.3, 0.4, 0.7),
            (2, 0.3, 0.7, 0.6, 1.0),
            (3, -1.1, 1.0, 0.5, 0.9),
            (3, -0.6, 0.85, 0.8, 1.0),
        )
    )
    design = np.zeros((len(observations), 5), dtype=np.float64)
    response = np.asarray([item.value for item in observations], dtype=np.float64)
    weights = np.empty(len(observations), dtype=np.float64)
    for index, item in enumerate(observations):
        design[index, 0] = 1.0
        design[index, item.axis_index + 1] = item.source_loading
        variance = item.standard_error**2 + configuration.standard_error_floor**2
        weights[index] = item.quality_weight / variance
    hessian = design.T @ (weights[:, None] * design)
    hessian += np.diag(
        [configuration.intercept_ridge] + [configuration.axis_ridge] * 4
    )
    rhs = design.T @ (weights * response)
    constraint = np.asarray([0.0, 1.0, 1.0, 1.0, 1.0])
    kkt = np.block(
        [
            [hessian, constraint[:, None]],
            [constraint[None, :], np.zeros((1, 1))],
        ]
    )
    oracle = np.linalg.solve(kkt, np.concatenate((rhs, [0.0])))[:5]

    outcome = solve_constrained_latent(observations, configuration)

    assert outcome.converged
    assert np.asarray((outcome.intercept, *outcome.axis_values)) == pytest.approx(
        oracle, abs=1e-8
    )
    assert outcome.sum_to_zero_residual <= 1e-12


def test_input_order_and_global_shift_do_not_change_axis_contrasts() -> None:
    configuration = _configuration(intercept_ridge=1e-9)
    observations = tuple(
        _observation(axis, 2.0 + axis_value + offset * 0.02, error=0.3)
        for axis, axis_value in enumerate((1.2, -0.8, 0.4, -0.8))
        for offset in range(8)
    )
    forward = solve_constrained_latent(observations, configuration)
    reverse = solve_constrained_latent(tuple(reversed(observations)), configuration)
    shifted = solve_constrained_latent(
        tuple(
            _observation(
                item.axis_index,
                item.value + 3.0,
                loading=item.source_loading,
                error=item.standard_error,
                quality=item.quality_weight,
            )
            for item in observations
        ),
        configuration,
    )

    assert forward.converged and reverse.converged and shifted.converged
    assert reverse.axis_values == pytest.approx(forward.axis_values, abs=1e-9)
    assert shifted.axis_values == pytest.approx(forward.axis_values, abs=1e-8)
    assert shifted.intercept - forward.intercept == pytest.approx(3.0, abs=1e-8)


def test_nonbinding_censored_upper_limit_cannot_become_negative_evidence() -> None:
    configuration = _configuration()
    base = tuple(
        _observation(axis, value, error=0.35)
        for axis, value in enumerate((1.0, -1.0, 0.5, -0.5))
        for _ in range(6)
    )
    baseline = solve_constrained_latent(base, configuration)
    nonbinding = solve_constrained_latent(
        (*base, _observation(0, 10.0, state="left_censored", error=0.1)),
        configuration,
    )
    binding = solve_constrained_latent(
        (*base, _observation(0, -3.0, state="left_censored", error=0.1)),
        configuration,
    )

    assert nonbinding.axis_values == pytest.approx(baseline.axis_values, abs=1e-9)
    assert nonbinding.intercept == pytest.approx(baseline.intercept, abs=1e-9)
    assert binding.axis_values[0] < baseline.axis_values[0]


def test_huber_fit_limits_a_single_extreme_protein_driver() -> None:
    base = tuple(
        _observation(axis, value, error=0.25)
        for axis, value in enumerate((0.8, -0.8, 0.4, -0.4))
        for _ in range(12)
    )
    contaminated = (*base, _observation(0, 20.0, error=0.25))
    robust = solve_constrained_latent(contaminated, _configuration(huber_delta=1.0))
    quadratic = solve_constrained_latent(
        contaminated,
        _configuration(huber_delta=1_000.0),
    )

    assert robust.converged and quadratic.converged
    assert abs(robust.axis_values[0] - 0.8) < abs(quadratic.axis_values[0] - 0.8)


def test_trace_is_monotone_and_constraint_is_preserved() -> None:
    observations = tuple(
        _observation(axis, math.sin(axis + replicate / 3.0), error=0.2 + replicate / 50)
        for axis in range(4)
        for replicate in range(10)
    )
    outcome = solve_constrained_latent(observations, _configuration())

    assert outcome.objective_trace
    for index, item in enumerate(outcome.objective_trace):
        assert item.accepted_objective <= item.baseline_objective + 1e-12
        if index:
            assert item.baseline_objective == pytest.approx(
                outcome.objective_trace[index - 1].accepted_objective,
                abs=1e-12,
            )
    assert outcome.objective == pytest.approx(
        outcome.objective_trace[-1].accepted_objective,
        abs=1e-12,
    )
    assert outcome.sum_to_zero_residual <= 1e-12


@pytest.mark.parametrize(
    "item",
    [
        lambda: _observation(4, 0.0),
        lambda: _observation(0, math.inf),
        lambda: _observation(0, 0.0, loading=0.0),
        lambda: _observation(0, 0.0, error=0.0),
        lambda: _observation(0, 0.0, quality=0.0),
    ],
)
def test_invalid_solver_observations_fail_closed(item: object) -> None:
    with pytest.raises(ValueError):
        item()  # type: ignore[operator]


def test_solver_requires_active_evidence() -> None:
    with pytest.raises(ValueError, match="at least one active observation"):
        solve_constrained_latent((), _configuration())

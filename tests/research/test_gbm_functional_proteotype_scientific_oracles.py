"""Synthetic scientific self-consistency oracles for the GBM proteotype fit.

These deterministic tests validate numerical and statistical software behavior on
constructed data.  They use no external cohort and provide no biological, clinical,
or interval-calibration validation.  In particular, the correlated perturbation
check demonstrates a known limitation; it does not claim that the runtime models
cross-protein covariance.
"""

from __future__ import annotations

import itertools
import math
from typing import Literal

import numpy as np
import pytest

from glio_proteogen.research.gbm_functional_proteotype.solver import (
    SolverConfiguration,
    SolverObservation,
    SolverOutcome,
    objective,
    solve_constrained_latent,
)
from glio_proteogen.research.gbm_functional_proteotype.statistics import (
    stratified_permutation_rank_test,
)


def _configuration(
    *,
    huber_delta: float = 1.345,
    standard_error_floor: float = 0.10,
    axis_ridge: float = 1e-3,
    intercept_ridge: float = 1e-8,
) -> SolverConfiguration:
    return SolverConfiguration(
        huber_delta=huber_delta,
        standard_error_floor=standard_error_floor,
        axis_ridge=axis_ridge,
        intercept_ridge=intercept_ridge,
        damping=1.0,
        tolerance=1e-10,
        gradient_tolerance=1e-9,
        max_iterations=256,
        backtracking_factor=0.5,
        backtracking_steps=32,
        objective_increase_tolerance=1e-12,
    )


def _observation(
    axis: int,
    value: float,
    *,
    state: Literal["observed", "left_censored"] = "observed",
    error: float = 0.20,
    quality: float = 1.0,
) -> SolverObservation:
    return SolverObservation(
        axis_index=axis,
        source_loading=1.0,
        state=state,
        value=value,
        standard_error=error,
        quality_weight=quality,
    )


def _balanced_observations(
    coordinates: tuple[float, float, float, float],
    *,
    intercept: float,
    repeats: int = 12,
    error: float = 0.15,
) -> tuple[SolverObservation, ...]:
    centered_offsets = np.linspace(-0.03, 0.03, repeats, dtype=np.float64)
    return tuple(
        _observation(
            axis,
            intercept + coordinate + float(offset),
            error=error,
        )
        for axis, coordinate in enumerate(coordinates)
        for offset in centered_offsets
    )


def _parameters(outcome: SolverOutcome) -> np.ndarray:
    return np.asarray(
        (outcome.intercept, *outcome.axis_values),
        dtype=np.float64,
    )


def test_huber_cap_limits_outlier_displacement_relative_to_uncapped_fit() -> None:
    """A single gross error has bounded influence only in the Huber fit."""

    truth = (1.0, -1.0, 0.4, -0.4)
    clean = _balanced_observations(truth, intercept=0.25)
    contaminated = (*clean, _observation(0, 25.0, error=0.15))

    robust = solve_constrained_latent(contaminated, _configuration())
    uncapped = solve_constrained_latent(
        contaminated,
        _configuration(huber_delta=1e6),
    )
    robust_error = float(np.max(np.abs(np.asarray(robust.axis_values) - truth)))
    uncapped_error = float(np.max(np.abs(np.asarray(uncapped.axis_values) - truth)))

    assert robust.converged and uncapped.converged
    assert robust_error < 0.05
    assert uncapped_error > 1.0
    assert robust_error < uncapped_error / 20.0


def test_left_censor_binding_and_nonbinding_objective_oracle() -> None:
    """An upper limit is silent below the limit and one-sided above it."""

    configuration = _configuration()
    truth = (0.8, -0.8, 0.3, -0.3)
    base = _balanced_observations(truth, intercept=0.20, repeats=8)
    baseline = solve_constrained_latent(base, configuration)
    baseline_parameters = _parameters(baseline)
    baseline_prediction = baseline.intercept + baseline.axis_values[0]
    nonbinding_limit = baseline_prediction + 2.0
    binding_limit = baseline_prediction - 0.50
    nonbinding = _observation(
        0,
        nonbinding_limit,
        state="left_censored",
        error=0.20,
    )
    binding = _observation(
        0,
        binding_limit,
        state="left_censored",
        error=0.20,
    )

    base_objective = objective(baseline_parameters, base, configuration)
    assert objective(
        baseline_parameters,
        (*base, nonbinding),
        configuration,
    ) == pytest.approx(base_objective, abs=1e-14)
    assert objective(baseline_parameters, (*base, binding), configuration) > base_objective

    nonbinding_fit = solve_constrained_latent((*base, nonbinding), configuration)
    binding_fit = solve_constrained_latent((*base, binding), configuration)
    binding_prediction = binding_fit.intercept + binding_fit.axis_values[0]

    assert _parameters(nonbinding_fit) == pytest.approx(baseline_parameters, abs=1e-9)
    assert binding_limit < binding_prediction < baseline_prediction


def test_reported_heteroscedastic_errors_control_relative_influence() -> None:
    """This checks inverse-error weighting, not real-proteome calibration."""

    truth = np.asarray((0.9, -0.9, 0.35, -0.35), dtype=np.float64)
    intercept = 0.20
    low_error_offsets = np.linspace(-0.025, 0.025, 8, dtype=np.float64)
    high_error_bias = np.asarray((1.6, -1.6, 1.0, -1.0), dtype=np.float64)
    heteroscedastic: list[SolverObservation] = []
    falsely_homoscedastic: list[SolverObservation] = []
    for axis, coordinate in enumerate(truth):
        for offset in low_error_offsets:
            precise_value = intercept + float(coordinate + offset)
            noisy_value = intercept + float(coordinate + high_error_bias[axis] + 3 * offset)
            heteroscedastic.extend(
                (
                    _observation(axis, precise_value, error=0.08),
                    _observation(axis, noisy_value, error=1.20),
                )
            )
            falsely_homoscedastic.extend(
                (
                    _observation(axis, precise_value, error=0.08),
                    _observation(axis, noisy_value, error=0.08),
                )
            )

    configuration = _configuration(huber_delta=1e6)
    weighted = solve_constrained_latent(tuple(heteroscedastic), configuration)
    mislabeled = solve_constrained_latent(tuple(falsely_homoscedastic), configuration)
    weighted_error = float(np.max(np.abs(np.asarray(weighted.axis_values) - truth)))
    mislabeled_error = float(np.max(np.abs(np.asarray(mislabeled.axis_values) - truth)))

    assert weighted.converged and mislabeled.converged
    assert weighted_error < 0.05
    assert mislabeled_error > 0.70
    assert weighted_error < mislabeled_error / 20.0


def test_correlated_common_mode_is_absorbed_but_axis_block_bias_is_not_removed() -> None:
    """The model has common-offset invariance, not covariance robustness."""

    truth = (0.9, -0.9, 0.35, -0.35)
    base = _balanced_observations(truth, intercept=0.20, repeats=8)
    common_shift = 0.75
    block_shifts = (0.50, -0.50, 0.25, -0.25)
    common = tuple(
        _observation(item.axis_index, item.value + common_shift, error=item.standard_error)
        for item in base
    )
    blocked = tuple(
        _observation(
            item.axis_index,
            item.value + block_shifts[item.axis_index],
            error=item.standard_error,
        )
        for item in base
    )
    configuration = _configuration(huber_delta=1e6, intercept_ridge=1e-12)

    baseline = solve_constrained_latent(base, configuration)
    common_fit = solve_constrained_latent(common, configuration)
    blocked_fit = solve_constrained_latent(blocked, configuration)
    block_delta = np.asarray(blocked_fit.axis_values) - np.asarray(baseline.axis_values)

    assert baseline.converged and common_fit.converged and blocked_fit.converged
    assert common_fit.axis_values == pytest.approx(baseline.axis_values, abs=1e-8)
    assert common_fit.intercept - baseline.intercept == pytest.approx(
        common_shift,
        abs=1e-8,
    )
    assert block_delta == pytest.approx(block_shifts, abs=1e-4)
    assert float(np.max(np.abs(block_delta))) > 0.49


def _rank_biserial_oracle(
    values: np.ndarray,
    labels: np.ndarray,
    axis: int,
) -> float:
    target = tuple(float(value) for value in values[labels == axis])
    background = tuple(float(value) for value in values[labels != axis])
    u_statistic = math.fsum(
        1.0 if left > right else 0.5 if left == right else 0.0
        for left, right in itertools.product(target, background)
    )
    return 2.0 * u_statistic / (len(target) * len(background)) - 1.0


def _exhaustive_stratified_oracle(
    values: np.ndarray,
    labels: np.ndarray,
    strata: tuple[tuple[int, ...], ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Enumerate a tiny null without using production ranking or permutation helpers."""

    observed = np.asarray(
        [_rank_biserial_oracle(values, labels, axis) for axis in range(4)],
        dtype=np.float64,
    )
    stratum_orders = tuple(
        tuple(itertools.permutations(tuple(int(labels[index]) for index in indices)))
        for indices in strata
    )
    null_rows: list[tuple[float, float, float, float]] = []
    for selected_orders in itertools.product(*stratum_orders):
        permuted = labels.copy()
        for indices, selected in zip(strata, selected_orders, strict=True):
            permuted[np.asarray(indices, dtype=np.int64)] = selected
        row = tuple(_rank_biserial_oracle(values, permuted, axis) for axis in range(4))
        null_rows.append((row[0], row[1], row[2], row[3]))
    null = np.asarray(null_rows, dtype=np.float64)
    exact_p = np.mean(np.abs(null) >= np.abs(observed), axis=0)
    return observed, exact_p, np.std(null, axis=0, ddof=0)


def test_monte_carlo_permutation_matches_independent_exhaustive_small_null() -> None:
    values = np.asarray((3.2, -0.7, 1.1, 0.2, 2.0, -1.4, 0.5, 1.8))
    labels = np.asarray((0, 1, 2, 3, 0, 1, 2, 3), dtype=np.int64)
    source_ranks = np.asarray((1, 2, 3, 4, 39, 40, 41, 42), dtype=np.int64)
    strata = ((0, 1, 2, 3), (4, 5, 6, 7))
    observed, exact_p, exact_standard_deviation = _exhaustive_stratified_oracle(
        values,
        labels,
        strata,
    )

    result = stratified_permutation_rank_test(
        values,
        labels,
        source_ranks,
        replicates=16_383,
        seed=0x5E1F_C0DE,
    )
    actual_statistics = np.asarray(
        [statistic.rank_biserial for statistic in result.statistics],
        dtype=np.float64,
    )

    assert actual_statistics == pytest.approx(observed, abs=1e-15)
    assert np.asarray(result.p_values) == pytest.approx(exact_p, abs=0.02)
    assert np.asarray(result.null_standard_deviations) == pytest.approx(
        exact_standard_deviation,
        abs=0.02,
    )


def _expand_constrained(reduced: np.ndarray) -> np.ndarray:
    return np.asarray(
        (reduced[0], reduced[1], reduced[2], reduced[3], -math.fsum(reduced[1:])),
        dtype=np.float64,
    )


def _black_box_mesh_oracle(
    observations: tuple[SolverObservation, ...],
    configuration: SolverConfiguration,
) -> tuple[np.ndarray, float]:
    """Minimize the public objective by exhaustive local meshes, independent of IRLS."""

    reduced = np.zeros(4, dtype=np.float64)
    best_value = objective(_expand_constrained(reduced), observations, configuration)
    moves = tuple(itertools.product((-1.0, 0.0, 1.0), repeat=4))
    for step in (2.0, 0.5, 0.125, 0.03125, 0.0078125, 0.001953125, 0.00048828125, 0.0001220703125):
        for _ in range(32):
            best_point = reduced
            sweep_value = best_value
            for move in moves:
                candidate = reduced + step * np.asarray(move, dtype=np.float64)
                candidate_value = objective(
                    _expand_constrained(candidate),
                    observations,
                    configuration,
                )
                if candidate_value < sweep_value - 1e-14:
                    best_point = candidate
                    sweep_value = candidate_value
            if np.array_equal(best_point, reduced):
                break
            reduced = best_point
            best_value = sweep_value
    expanded = _expand_constrained(reduced)
    return expanded, objective(expanded, observations, configuration)


def test_robust_censored_solution_matches_black_box_convex_mesh_oracle() -> None:
    """SciPy is not locked; a small objective-only mesh is the independent oracle."""

    configuration = _configuration(
        huber_delta=1.1,
        standard_error_floor=0.20,
        axis_ridge=0.05,
        intercept_ridge=0.02,
    )
    rows: tuple[tuple[int, float, Literal["observed", "left_censored"], float, float], ...] = (
        (0, 0.90, "observed", 0.25, 1.00),
        (0, 1.15, "observed", 0.35, 0.80),
        (0, 5.00, "observed", 0.20, 0.70),
        (0, -0.10, "left_censored", 0.30, 0.90),
        (1, -0.85, "observed", 0.25, 1.00),
        (1, -0.65, "observed", 0.40, 0.70),
        (2, 0.25, "observed", 0.20, 1.00),
        (2, 0.45, "observed", 0.35, 0.90),
        (2, 2.00, "left_censored", 0.20, 1.00),
        (3, -0.50, "observed", 0.25, 1.00),
        (3, -0.30, "observed", 0.40, 0.80),
    )
    observations = tuple(
        _observation(axis, value, state=state, error=error, quality=quality)
        for axis, value, state, error, quality in rows
    )

    outcome = solve_constrained_latent(observations, configuration)
    oracle_parameters, oracle_objective = _black_box_mesh_oracle(
        observations,
        configuration,
    )

    assert outcome.converged
    assert outcome.objective == pytest.approx(oracle_objective, abs=2e-7)
    assert _parameters(outcome) == pytest.approx(oracle_parameters, abs=5e-4)
    assert abs(math.fsum(outcome.axis_values)) <= 1e-12

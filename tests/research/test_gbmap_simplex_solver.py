"""Independent oracles for the source-unfitted GBmap RNA-mixture solver."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution.simplex import (
    reference_mixture_gradient,
    reference_mixture_objective,
    reference_signature_condition_number,
    solve_reference_mixture,
    verify_objective_trace,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)

_SIGNATURES = np.asarray(
    [
        [0.70, 0.10],
        [0.20, 0.30],
        [0.10, 0.60],
    ],
    dtype=np.float64,
)
_BACKGROUND = np.asarray([0.30, 0.30, 0.40], dtype=np.float64)


def _objective_from_combined(weights: np.ndarray, counts: np.ndarray) -> float:
    return reference_mixture_objective(
        counts,
        _SIGNATURES,
        _BACKGROUND,
        weights[:2],
        weights[2:],
        concentration=80.0,
        lambda_mass=0.04,
        lambda_shape=0.1,
    )


def test_full_gradient_matches_independent_simplex_finite_differences() -> None:
    counts = np.asarray([620, 220, 160], dtype=np.int64)
    weights = np.asarray([0.45, 0.35, 0.05, 0.07, 0.08], dtype=np.float64)
    gradient = reference_mixture_gradient(
        counts,
        _SIGNATURES,
        _BACKGROUND,
        weights[:2],
        weights[2:],
        concentration=80.0,
        lambda_mass=0.04,
        lambda_shape=0.1,
    )
    epsilon = 1e-6
    for index in range(weights.size - 1):
        plus = weights.copy()
        minus = weights.copy()
        plus[index] += epsilon
        plus[-1] -= epsilon
        minus[index] -= epsilon
        minus[-1] += epsilon
        numerical = (
            _objective_from_combined(plus, counts) - _objective_from_combined(minus, counts)
        ) / (2.0 * epsilon)
        assert numerical == pytest.approx(gradient[index] - gradient[-1], rel=2e-6, abs=2e-8)


def _refined_grid_oracle(counts: np.ndarray) -> float:
    """Independently refine the three-part simplex without solver gradients."""

    signature = np.asarray([[0.78], [0.22]], dtype=np.float64)
    background = np.asarray([0.35, 0.65], dtype=np.float64)

    def objective(known: float, first_unknown: float) -> float:
        second_unknown = 1.0 - known - first_unknown
        if min(known, first_unknown, second_unknown) <= 0.0:
            return float("inf")
        return reference_mixture_objective(
            counts,
            signature,
            background,
            np.asarray([known], dtype=np.float64),
            np.asarray([first_unknown, second_unknown], dtype=np.float64),
            concentration=60.0,
            lambda_mass=0.025,
            lambda_shape=0.08,
        )

    best_known = 0.5
    best_unknown = 0.25
    best_objective = objective(best_known, best_unknown)
    radius = 0.5
    for _ in range(9):
        known_grid = np.linspace(max(1e-8, best_known - radius), min(1.0, best_known + radius), 31)
        unknown_grid = np.linspace(
            max(1e-8, best_unknown - radius),
            min(1.0, best_unknown + radius),
            31,
        )
        for known in known_grid:
            for first_unknown in unknown_grid:
                candidate = objective(float(known), float(first_unknown))
                if candidate < best_objective:
                    best_known = float(known)
                    best_unknown = float(first_unknown)
                    best_objective = candidate
        radius /= 10.0
    return best_objective


def test_solver_matches_independent_refined_simplex_oracle() -> None:
    counts = np.asarray([690, 310], dtype=np.int64)
    signature = np.asarray([[0.78], [0.22]], dtype=np.float64)
    background = np.asarray([0.35, 0.65], dtype=np.float64)
    solution = solve_reference_mixture(
        counts,
        signature,
        background,
        concentration=60.0,
        lambda_mass=0.025,
        lambda_shape=0.08,
    )

    assert solution.converged
    assert solution.iterations <= 500
    assert solution.kkt_residual <= 1e-7
    assert solution.objective <= _refined_grid_oracle(counts) + 1e-7
    assert verify_objective_trace(solution)
    assert np.all(np.diff([item.objective for item in solution.trace]) <= 1e-12)


def test_unknown_channel_retains_mass_for_an_omitted_profile() -> None:
    counts = np.asarray([50, 50, 900], dtype=np.int64)
    solution = solve_reference_mixture(
        counts,
        _SIGNATURES,
        _BACKGROUND,
        concentration=100.0,
        lambda_mass=0.01,
        lambda_shape=0.01,
    )

    assert solution.converged
    assert solution.iterations <= 500
    assert solution.unknown_mass >= 0.35
    assert float(solution.unknown_gene_mass[2]) > float(np.sum(solution.known_rna_weights))
    assert float(np.sum(solution.known_rna_weights)) == pytest.approx(
        1.0 - solution.unknown_mass,
        abs=2e-12,
    )
    assert float(np.sum(solution.fitted_probabilities)) == pytest.approx(1.0, abs=2e-12)
    assert not solution.known_rna_weights.flags.writeable
    assert not solution.unknown_gene_mass.flags.writeable


def test_lineage_permutation_only_permutes_the_known_solution() -> None:
    counts = np.asarray([480, 250, 270], dtype=np.int64)
    original = solve_reference_mixture(
        counts,
        _SIGNATURES,
        _BACKGROUND,
        concentration=120.0,
        lambda_mass=0.08,
        lambda_shape=0.1,
    )
    reversed_fit = solve_reference_mixture(
        counts,
        _SIGNATURES[:, ::-1],
        _BACKGROUND,
        concentration=120.0,
        lambda_mass=0.08,
        lambda_shape=0.1,
    )

    assert original.converged and reversed_fit.converged
    assert reversed_fit.known_rna_weights == pytest.approx(
        original.known_rna_weights[::-1], abs=2e-10
    )
    assert reversed_fit.unknown_gene_mass == pytest.approx(original.unknown_gene_mass, abs=2e-10)
    assert reversed_fit.objective == pytest.approx(original.objective, abs=2e-12)


def test_nonidentifiable_signatures_fail_closed_before_emitting_weights() -> None:
    identical = np.asarray(
        [
            [0.6, 0.6],
            [0.3, 0.3],
            [0.1, 0.1],
        ],
        dtype=np.float64,
    )
    assert reference_signature_condition_number(identical) == float("inf")
    with pytest.raises(ValueError, match="not identifiable"):
        solve_reference_mixture(
            np.asarray([600, 300, 100], dtype=np.int64),
            identical,
            _BACKGROUND,
            concentration=80.0,
            lambda_mass=0.1,
            lambda_shape=0.1,
        )


def test_trace_verification_detects_a_resealed_nonmonotone_record() -> None:
    solution = solve_reference_mixture(
        np.asarray([480, 250, 270], dtype=np.int64),
        _SIGNATURES,
        _BACKGROUND,
        concentration=120.0,
        lambda_mass=0.08,
        lambda_shape=0.1,
    )
    assert verify_objective_trace(solution)
    forged_first = replace(solution.trace[0], objective=solution.initial_objective + 1.0)
    forged = replace(solution, trace=(forged_first, *solution.trace[1:]))
    assert verify_objective_trace(forged) is False


def test_precancelled_fit_stops_at_the_first_numerical_boundary() -> None:
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        solve_reference_mixture(
            np.asarray([480, 250, 270], dtype=np.int64),
            _SIGNATURES,
            _BACKGROUND,
            concentration=120.0,
            lambda_mass=0.08,
            lambda_shape=0.1,
            cancellation=cancellation,
        )


@pytest.mark.parametrize(
    ("signatures", "background", "message"),
    [
        (np.asarray([[True], [False]]), np.asarray([0.5, 0.5]), "numeric"),
        (np.asarray([[0.7], [0.4]]), np.asarray([0.5, 0.5]), "sum to one"),
        (np.asarray([[0.7], [0.3]]), np.asarray([1.0, 0.0]), "strictly positive"),
    ],
)
def test_probability_inputs_are_strict(
    signatures: np.ndarray,
    background: np.ndarray,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        solve_reference_mixture(
            np.asarray([7, 3], dtype=np.int64),
            signatures,
            background,
            concentration=20.0,
            lambda_mass=0.1,
            lambda_shape=0.1,
        )

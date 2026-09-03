"""Independent oracles for donor/study-shrunk GBmap DM fitting."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from unittest.mock import patch

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution.dm import (
    dirichlet_multinomial_per_count_nll,
    dm_probability_gradient,
    dm_probability_hessian_diagonal,
)
from glio_proteogen.research.gbmap_deconvolution.errors import GbmapInputError
from glio_proteogen.research.gbmap_deconvolution.hierarchy import (
    BACKGROUND_REGULARIZATION,
    MAXIMUM_CONCENTRATION,
    MINIMUM_CONCENTRATION,
    LineageHierarchyFit,
    _dm_per_count_nll_prevalidated,
    _gradient,
    _HierarchyObjectiveEvaluator,
    _log_concentration_derivatives,
    _objective,
    _study_dm_gradient,
    _study_dm_hessian_diagonal,
    _study_gradient,
    _validated_data,
    fit_lineage_hierarchy,
    lineage_hierarchy_gradient,
    lineage_hierarchy_objective,
    study_balanced_global_signature,
    verify_hierarchy_trace,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)

_COUNTS = np.asarray(
    [
        [700, 200, 100],
        [680, 220, 100],
        [720, 180, 100],
        [300, 500, 200],
        [320, 480, 200],
        [280, 520, 200],
    ],
    dtype=np.int64,
)
_STUDIES = ("study-a",) * 3 + ("study-b",) * 3
_BACKGROUND = np.asarray([1.0 / 3.0] * 3, dtype=np.float64)


@lru_cache(maxsize=1)
def _fitted_hierarchy() -> LineageHierarchyFit:
    return fit_lineage_hierarchy(
        _COUNTS,
        _STUDIES,
        _BACKGROUND,
        shrinkage=2.0,
    )


def test_closed_form_global_signature_gives_every_study_equal_weight() -> None:
    signatures = np.asarray(
        [
            [0.80, 0.10, 0.10],
            [0.10, 0.80, 0.10],
        ],
        dtype=np.float64,
    )
    shrinkage = 2.0
    actual = study_balanced_global_signature(signatures, _BACKGROUND, shrinkage)
    expected = (
        shrinkage * np.sum(signatures, axis=0) + BACKGROUND_REGULARIZATION * _BACKGROUND
    ) / (shrinkage * signatures.shape[0] + BACKGROUND_REGULARIZATION)

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=2e-15)
    assert float(np.sum(actual)) == pytest.approx(1.0, abs=2e-15)
    assert actual[0] == pytest.approx(actual[1], abs=2e-15)


def test_hierarchy_gradient_matches_simplex_preserving_finite_differences() -> None:
    signatures = np.asarray(
        [
            [0.60, 0.28, 0.12],
            [0.32, 0.48, 0.20],
        ],
        dtype=np.float64,
    )
    concentration = 13.0
    shrinkage = 2.0
    gradient = lineage_hierarchy_gradient(
        _COUNTS,
        _STUDIES,
        signatures,
        _BACKGROUND,
        concentration=concentration,
        shrinkage=shrinkage,
    )
    epsilon = 1e-6
    for study in range(signatures.shape[0]):
        for gene in range(signatures.shape[1] - 1):
            direction = np.zeros_like(signatures)
            direction[study, gene] = 1.0
            direction[study, -1] = -1.0
            plus = lineage_hierarchy_objective(
                _COUNTS,
                _STUDIES,
                signatures + epsilon * direction,
                _BACKGROUND,
                concentration=concentration,
                shrinkage=shrinkage,
            )
            minus = lineage_hierarchy_objective(
                _COUNTS,
                _STUDIES,
                signatures - epsilon * direction,
                _BACKGROUND,
                concentration=concentration,
                shrinkage=shrinkage,
            )
            numerical = (plus - minus) / (2.0 * epsilon)
            expected = float(gradient[study, gene] - gradient[study, -1])
            assert numerical == pytest.approx(expected, rel=2e-5, abs=2e-8)


@pytest.mark.parametrize("shrinkage", [0.0, 2.0])
def test_coordinate_gradient_is_bit_exact_with_full_gradient(shrinkage: float) -> None:
    data = _validated_data(_COUNTS, _STUDIES, _BACKGROUND)
    signatures = np.asarray(
        [[0.60, 0.28, 0.12], [0.32, 0.48, 0.20]],
        dtype=np.float64,
    )
    complete = _gradient(data, signatures, 13.0, shrinkage)

    for study in range(signatures.shape[0]):
        np.testing.assert_array_equal(
            _study_gradient(data, signatures, study, 13.0, shrinkage),
            complete[study],
        )


def test_vectorized_dm_kernel_matches_independent_scalar_functions() -> None:
    counts = np.asarray(
        [[30, 5, 2, 1], [4, 25, 3, 2], [8, 7, 20, 1]],
        dtype=np.int64,
    )
    probabilities = np.asarray([0.45, 0.30, 0.20, 0.05], dtype=np.float64)
    concentration = 17.3

    expected_nll = tuple(
        dirichlet_multinomial_per_count_nll(row, probabilities, concentration) for row in counts
    )
    expected_gradient = sum(
        (dm_probability_gradient(row, probabilities, concentration) for row in counts),
        start=np.zeros(4, dtype=np.float64),
    )
    expected_curvature = sum(
        (dm_probability_hessian_diagonal(row, probabilities, concentration) for row in counts),
        start=np.zeros(4, dtype=np.float64),
    )

    np.testing.assert_allclose(
        tuple(_dm_per_count_nll_prevalidated(row, probabilities, concentration) for row in counts),
        expected_nll,
        rtol=2e-12,
        atol=2e-12,
    )
    np.testing.assert_allclose(
        _study_dm_gradient(counts, probabilities, concentration),
        expected_gradient,
        rtol=2e-12,
        atol=2e-12,
    )
    np.testing.assert_allclose(
        _study_dm_hessian_diagonal(counts, probabilities, concentration),
        expected_curvature,
        rtol=2e-12,
        atol=2e-12,
    )


def test_log_concentration_derivatives_match_objective_finite_differences() -> None:
    data = _validated_data(_COUNTS, _STUDIES, _BACKGROUND)
    signatures = np.asarray(
        [[0.70, 0.20, 0.10], [0.30, 0.50, 0.20]],
        dtype=np.float64,
    )
    concentration = 13.0
    log_concentration = np.log(concentration)
    epsilon = 1e-5
    gradient, curvature = _log_concentration_derivatives(
        data,
        signatures,
        concentration,
    )
    center = _objective(data, signatures, concentration, 2.0)
    below = _objective(data, signatures, float(np.exp(log_concentration - epsilon)), 2.0)
    above = _objective(data, signatures, float(np.exp(log_concentration + epsilon)), 2.0)

    numerical_gradient = (above - below) / (2.0 * epsilon)
    numerical_curvature = (above - 2.0 * center + below) / (epsilon * epsilon)
    assert gradient == pytest.approx(numerical_gradient, rel=2e-6, abs=2e-8)
    assert curvature == pytest.approx(numerical_curvature, rel=2e-3, abs=2e-4)


def test_cached_objective_is_bit_exact_across_signature_and_concentration_changes() -> None:
    data = _validated_data(_COUNTS, _STUDIES, _BACKGROUND)
    evaluator = _HierarchyObjectiveEvaluator(data)
    baseline = np.asarray(
        [[0.70, 0.20, 0.10], [0.30, 0.50, 0.20]],
        dtype=np.float64,
    )
    changed = baseline.copy()
    changed[1] = np.asarray([0.31, 0.48, 0.21], dtype=np.float64)

    cases = (
        (baseline, 13.0),
        (baseline.copy(), 13.0),
        (changed, 13.0),
        (changed.copy(), 17.0),
    )
    expected = tuple(
        _objective(data, signatures, concentration, 2.0) for signatures, concentration in cases
    )
    with patch(
        "glio_proteogen.research.gbmap_deconvolution.hierarchy._dm_per_count_nll_prevalidated",
        wraps=_dm_per_count_nll_prevalidated,
    ) as donor_kernel:
        observed: list[float] = []
        cumulative_calls: list[int] = []
        for signatures, concentration in cases:
            observed.append(evaluator.evaluate(signatures, concentration, 2.0))
            cumulative_calls.append(donor_kernel.call_count)

    assert tuple(observed) == expected
    assert cumulative_calls == [6, 6, 9, 15]


def test_fitted_hierarchy_closes_kkt_and_preserves_monotone_trace() -> None:
    fit = _fitted_hierarchy()

    assert fit.converged
    assert fit.iterations <= 100
    assert fit.kkt_residual <= 1e-6
    assert MINIMUM_CONCENTRATION <= fit.concentration <= MAXIMUM_CONCENTRATION
    assert fit.study_keys == ("study-a", "study-b")
    assert verify_hierarchy_trace(fit)
    assert all(
        later.objective <= earlier.objective + 1e-15
        for earlier, later in zip(fit.trace, fit.trace[1:], strict=False)
    )
    assert not fit.study_signatures.flags.writeable
    assert not fit.global_signature.flags.writeable
    assert float(np.sum(fit.global_signature)) == pytest.approx(1.0, abs=2e-12)


def test_optimized_hierarchy_preserves_locked_preoptimization_solution() -> None:
    fit = _fitted_hierarchy()

    # Accelerate/BLAS reduction order changes the last few descent steps across
    # operating systems.  Lock the scientifically meaningful endpoint more
    # tightly than the solver's 1e-6 KKT tolerance without requiring identical
    # floating-point instruction order.  Same-runtime replay and input-order
    # invariance remain bit-exact in the dedicated test below.
    np.testing.assert_allclose(
        fit.study_signatures,
        np.asarray(
            [
                [0.4683267420959967, 0.3412077565523813, 0.190465501351622],
                [0.46113766273334855, 0.346304878197036, 0.1925574590696155],
            ],
            dtype=np.float64,
        ),
        rtol=0.0,
        atol=1.0e-7,
    )
    assert fit.concentration == pytest.approx(11.782937550694719, rel=0.0, abs=5.0e-6)
    assert fit.objective == pytest.approx(0.0738415722718625, rel=0.0, abs=5.0e-13)
    assert fit.kkt_residual <= 2.0e-7
    assert 30 <= fit.iterations <= 35


def test_donor_and_study_input_order_cannot_change_the_fit() -> None:
    original = _fitted_hierarchy()
    order = np.asarray([5, 2, 4, 1, 3, 0], dtype=np.int64)
    reordered = fit_lineage_hierarchy(
        _COUNTS[order],
        tuple(_STUDIES[int(index)] for index in order),
        _BACKGROUND,
        shrinkage=2.0,
    )

    assert reordered.study_keys == original.study_keys
    np.testing.assert_array_equal(reordered.study_signatures, original.study_signatures)
    np.testing.assert_array_equal(reordered.global_signature, original.global_signature)
    assert reordered.concentration == original.concentration
    assert reordered.objective == original.objective
    assert reordered.trace == original.trace


def test_trace_forgery_is_detected_even_when_fit_shape_remains_valid() -> None:
    fit = _fitted_hierarchy()
    forged_record = replace(fit.trace[0], objective=fit.initial_objective + 1.0)
    forged = replace(fit, trace=(forged_record, *fit.trace[1:]))
    assert verify_hierarchy_trace(forged) is False


def test_precancelled_hierarchy_stops_before_fitting() -> None:
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        fit_lineage_hierarchy(
            _COUNTS,
            _STUDIES,
            _BACKGROUND,
            shrinkage=2.0,
            cancellation=cancellation,
        )


@pytest.mark.parametrize(
    ("counts", "studies", "background", "message"),
    [
        ([[True, 1, 1]], ("study",), [1 / 3] * 3, "exact"),
        ([[0, 0, 0]], ("study",), [1 / 3] * 3, "positive total"),
        ([[1, 1, 1]], (), [1 / 3] * 3, "one key per donor"),
        ([[1, 1, 1]], ("study",), [0.5, 0.5, 0.1], "sum to one"),
        ([[1, 1, 1]], ("study",), [0.5, 0.5, 0.0], "at least"),
    ],
)
def test_hierarchy_boundary_rejects_coercion_and_invalid_simplexes(
    counts: object,
    studies: tuple[str, ...],
    background: object,
    message: str,
) -> None:
    with pytest.raises(GbmapInputError, match=message):
        fit_lineage_hierarchy(
            counts,  # type: ignore[arg-type]
            studies,
            background,  # type: ignore[arg-type]
            shrinkage=2.0,
        )

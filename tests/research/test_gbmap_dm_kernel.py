"""Independent scientific oracles for the source-free GBmap DM kernel."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution.dm import (
    dirichlet_multinomial_log_likelihood,
    dirichlet_multinomial_per_count_nll,
    dm_probability_gradient,
    dm_probability_hessian_diagonal,
    sample_dirichlet_multinomial,
)
from glio_proteogen.research.gbmap_deconvolution.errors import GbmapInputError
from glio_proteogen.research.gbmap_deconvolution.numerics import digamma, trigamma

if TYPE_CHECKING:
    from collections.abc import Callable


def test_digamma_matches_hard_coded_high_precision_values() -> None:
    arguments = np.asarray([0.1, 0.5, 1.0, 1.5, 8.0, 10.0, 100.0], dtype=np.float64)
    expected = np.asarray(
        [
            -10.4237549404110767951682162190100254,
            -1.9635100260214234794409763329987556,
            -0.5772156649015328606065120900824024,
            0.0364899739785765205590236670012444,
            2.0156414779556099965363450527747404,
            2.2517525890667211076474561638858515,
            4.6001618527380874001986055855758507,
        ],
        dtype=np.float64,
    )

    actual = digamma(arguments.reshape(1, -1))

    assert isinstance(actual, np.ndarray)
    assert actual.shape == (1, arguments.size)
    assert actual.dtype == np.float64
    assert float(np.max(np.abs(actual.reshape(-1) - expected))) <= 2.0e-12
    assert isinstance(digamma(1.0), float)


def test_trigamma_matches_hard_coded_high_precision_values() -> None:
    arguments = np.asarray([0.1, 0.5, 1.0, 1.5, 8.0, 10.0, 100.0], dtype=np.float64)
    expected = np.asarray(
        [
            101.43329915079275881721545010641734,
            4.9348022005446793094172454999380756,
            1.6449340668482264364724151666460252,
            0.9348022005446793094172454999380756,
            0.13313701469403142513454668592040161,
            0.10516633568168574612220100690805593,
            0.010050166663333571395245668465701423,
        ],
        dtype=np.float64,
    )

    actual = trigamma(arguments)

    assert isinstance(actual, np.ndarray)
    assert actual.shape == arguments.shape
    assert actual.dtype == np.float64
    assert float(np.max(np.abs(actual - expected))) <= 5.0e-11
    assert isinstance(trigamma(1.0), float)


@pytest.mark.parametrize("function", [digamma, trigamma])
@pytest.mark.parametrize(
    "invalid",
    [0.0, -1.0, math.inf, -math.inf, math.nan, True, [], [1.0, math.nan], "1.0"],
)
def test_special_functions_reject_values_outside_positive_real_domain(
    function: Callable[[object], object],
    invalid: object,
) -> None:
    with pytest.raises(GbmapInputError):
        function(invalid)


def test_tiny_dirichlet_multinomial_oracle_is_hand_calculable() -> None:
    # With alpha=(1,1,1) and N=3, every weak count composition has PMF 1/10:
    # 3!/(2!1!0!) * Gamma(3)/Gamma(6) * Gamma(3)Gamma(2)Gamma(1) = 1/10.
    counts = np.asarray([2, 1, 0], dtype=np.int64)
    probabilities = np.asarray([1.0 / 3.0] * 3, dtype=np.float64)

    log_likelihood = dirichlet_multinomial_log_likelihood(counts, probabilities, 3.0)
    per_count_nll = dirichlet_multinomial_per_count_nll(counts, probabilities, 3.0)
    gradient = dm_probability_gradient(counts, probabilities, 3.0)
    hessian = dm_probability_hessian_diagonal(counts, probabilities, 3.0)

    assert log_likelihood == pytest.approx(math.log(0.1), abs=2.0e-15)
    assert per_count_nll == pytest.approx(-math.log(0.1) / 3.0, abs=1.0e-15)
    np.testing.assert_allclose(gradient, [-1.5, -1.0, 0.0], rtol=0.0, atol=2.0e-14)
    np.testing.assert_allclose(hessian, [3.75, 3.0, 0.0], rtol=0.0, atol=3.0e-13)


def test_non_integer_alpha_likelihood_matches_rising_factorial_oracle() -> None:
    # alpha=(1.4,2.1,3.5). The PMF is
    # 3 * (1.4 * 2.4) * 2.1 / (7 * 8 * 9) = 0.042 exactly.
    counts = np.asarray([2, 1, 0], dtype=np.int64)
    probabilities = np.asarray([0.2, 0.3, 0.5], dtype=np.float64)

    actual = dirichlet_multinomial_log_likelihood(counts, probabilities, 7.0)

    assert actual == pytest.approx(
        -3.1700856606987687461361442622292106,
        rel=0.0,
        abs=3.0e-15,
    )


def test_gradient_and_hessian_match_simplex_preserving_finite_differences() -> None:
    counts = np.asarray([7, 3, 5, 2], dtype=np.int64)
    probabilities = np.asarray([0.18, 0.27, 0.31, 0.24], dtype=np.float64)
    concentration = 11.0
    direction = np.asarray([1.0, -1.0, 0.0, 0.0], dtype=np.float64)
    gradient_step = 2.0e-6
    curvature_step = 2.0e-4

    gradient = dm_probability_gradient(counts, probabilities, concentration)
    plus = dirichlet_multinomial_per_count_nll(
        counts,
        probabilities + gradient_step * direction,
        concentration,
    )
    minus = dirichlet_multinomial_per_count_nll(
        counts,
        probabilities - gradient_step * direction,
        concentration,
    )
    finite_gradient = (plus - minus) / (2.0 * gradient_step)

    hessian = dm_probability_hessian_diagonal(counts, probabilities, concentration)
    baseline = dirichlet_multinomial_per_count_nll(counts, probabilities, concentration)
    curvature_plus = dirichlet_multinomial_per_count_nll(
        counts,
        probabilities + curvature_step * direction,
        concentration,
    )
    curvature_minus = dirichlet_multinomial_per_count_nll(
        counts,
        probabilities - curvature_step * direction,
        concentration,
    )
    finite_curvature = (curvature_plus - 2.0 * baseline + curvature_minus) / (
        curvature_step * curvature_step
    )

    assert finite_gradient == pytest.approx(float(gradient @ direction), rel=2.0e-6)
    assert finite_curvature == pytest.approx(float(hessian @ (direction * direction)), rel=2e-5)
    assert bool(np.all(hessian >= 0.0))


@pytest.mark.parametrize(
    "counts",
    [
        [],
        [[1, 2]],
        [True, 1],
        [1.0, 2.0],
        [1, -1],
        [1, math.nan],
        [1, math.inf],
    ],
)
def test_likelihood_rejects_invalid_counts(counts: object) -> None:
    with pytest.raises(GbmapInputError):
        dirichlet_multinomial_log_likelihood(counts, [0.5, 0.5], 4.0)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "probabilities",
    [
        [],
        [[0.5, 0.5]],
        [True, 0.5],
        [0.5, 0.4],
        [0.5, 0.5, 1.0e-14],
        [0.0, 1.0],
        [-0.1, 1.1],
        [math.nan, 0.5],
        [math.inf, 0.5],
    ],
)
def test_likelihood_rejects_invalid_probability_vectors(probabilities: object) -> None:
    with pytest.raises(GbmapInputError):
        dirichlet_multinomial_log_likelihood([1, 1], probabilities, 4.0)  # type: ignore[arg-type]


@pytest.mark.parametrize("concentration", [0.0, -1.0, math.nan, math.inf, True, "4"])
def test_likelihood_rejects_invalid_concentration(concentration: object) -> None:
    with pytest.raises(GbmapInputError):
        dirichlet_multinomial_log_likelihood(
            [1, 1],
            [0.5, 0.5],
            concentration,  # type: ignore[arg-type]
        )


def test_zero_depth_has_unit_probability_but_no_per_count_derivatives() -> None:
    counts = np.zeros(3, dtype=np.int64)
    probabilities = np.asarray([0.2, 0.3, 0.5], dtype=np.float64)

    assert dirichlet_multinomial_log_likelihood(counts, probabilities, 7.0) == 0.0
    with pytest.raises(GbmapInputError, match="per-count NLL"):
        dirichlet_multinomial_per_count_nll(counts, probabilities, 7.0)
    with pytest.raises(GbmapInputError, match="gradient"):
        dm_probability_gradient(counts, probabilities, 7.0)
    with pytest.raises(GbmapInputError, match="Hessian"):
        dm_probability_hessian_diagonal(counts, probabilities, 7.0)


def test_sampling_is_generator_deterministic_and_preserves_count_invariants() -> None:
    probabilities = np.asarray([0.2, 0.3, 0.5], dtype=np.float64)
    original = probabilities.copy()

    first = sample_dirichlet_multinomial(
        40,
        probabilities,
        7.0,
        np.random.default_rng(20260830),
    )
    second = sample_dirichlet_multinomial(
        40,
        probabilities,
        7.0,
        np.random.default_rng(20260830),
    )

    np.testing.assert_array_equal(first, [3, 19, 18])
    np.testing.assert_array_equal(second, first)
    np.testing.assert_array_equal(probabilities, original)
    assert first.dtype == np.int64
    assert int(np.sum(first, dtype=np.int64)) == 40
    assert bool(np.all(first >= 0))


def test_zero_count_sampling_is_degenerate_and_does_not_advance_generator() -> None:
    rng = np.random.default_rng(91)
    untouched = np.random.default_rng(91)

    sample = sample_dirichlet_multinomial(0, [0.4, 0.6], 5.0, rng)

    np.testing.assert_array_equal(sample, [0, 0])
    assert rng.random() == untouched.random()


def test_sampling_rejects_implicit_rng_and_non_integer_total() -> None:
    with pytest.raises(GbmapInputError, match="total_count"):
        sample_dirichlet_multinomial(3.0, [0.4, 0.6], 5.0, np.random.default_rng(1))  # type: ignore[arg-type]
    with pytest.raises(GbmapInputError, match="explicit"):
        sample_dirichlet_multinomial(3, [0.4, 0.6], 5.0, None)  # type: ignore[arg-type]

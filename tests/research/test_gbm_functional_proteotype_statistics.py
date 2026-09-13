"""Oracles for rank evidence and the fixed four-axis permutation family."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from glio_proteogen.research.gbm_functional_proteotype.statistics import (
    benjamini_hochberg,
    mann_whitney_rank_statistic,
    stratified_permutation_rank_test,
)


def _pairwise_u(target: tuple[float, ...], background: tuple[float, ...]) -> float:
    return sum(
        1.0 if left > right else 0.5 if left == right else 0.0
        for left, right in itertools.product(target, background)
    )


def test_mann_whitney_matches_brute_force_including_ties() -> None:
    values = np.asarray([3.0, 2.0, 2.0, -1.0, 2.0, 0.0, -1.0], dtype=np.float64)
    mask = np.asarray([True, True, False, True, False, False, False], dtype=np.bool_)
    result = mann_whitney_rank_statistic(values, mask)
    target = tuple(float(value) for value in values[mask])
    background = tuple(float(value) for value in values[~mask])
    expected_u = _pairwise_u(target, background)

    assert result.u_statistic == expected_u
    assert result.rank_biserial == pytest.approx(
        2.0 * expected_u / (len(target) * len(background)) - 1.0
    )


def test_benjamini_hochberg_matches_hand_calculated_family() -> None:
    assert benjamini_hochberg((0.01, 0.04, 0.03, 0.20)) == pytest.approx(
        (0.04, 0.05333333333333334, 0.05333333333333334, 0.20)
    )


def test_joint_stratified_permutation_is_deterministic_and_detects_planted_axis() -> None:
    rng = np.random.default_rng(991)
    axis_indices = np.repeat(np.arange(4, dtype=np.int64), 40)
    source_ranks = np.tile(np.arange(1, 41, dtype=np.int64), 4)
    values = rng.normal(0.0, 0.25, size=len(axis_indices))
    values[axis_indices == 0] += 1.5

    first = stratified_permutation_rank_test(
        values,
        axis_indices,
        source_ranks,
        replicates=255,
        seed=7123,
    )
    second = stratified_permutation_rank_test(
        values,
        axis_indices,
        source_ranks,
        replicates=255,
        seed=7123,
    )

    assert first == second
    assert first.statistics[0].rank_biserial > 0.9
    assert first.q_values[0] <= 0.02
    assert all(0.0 <= value <= 1.0 for value in first.p_values + first.q_values)
    assert all(value >= 0.0 for value in first.null_standard_deviations)


@pytest.mark.parametrize(
    ("p_values", "message"),
    [
        ((-0.1, 0.2), "finite probabilities"),
        ((0.1, float("nan")), "finite probabilities"),
    ],
)
def test_bh_rejects_invalid_probabilities(
    p_values: tuple[float, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        benjamini_hochberg(p_values)


def test_rank_test_rejects_missing_target_or_background() -> None:
    values = np.asarray([1.0, 2.0, 3.0], dtype=np.float64)
    with pytest.raises(ValueError, match="target and background"):
        mann_whitney_rank_statistic(values, np.ones(3, dtype=np.bool_))


def test_permutation_rejects_invalid_source_rank() -> None:
    values = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
    axes = np.asarray([0, 1, 2, 3], dtype=np.int64)
    ranks = np.asarray([1, 2, 3, 151], dtype=np.int64)
    with pytest.raises(ValueError, match="between one and 150"):
        stratified_permutation_rank_test(
            values,
            axes,
            ranks,
            replicates=8,
            seed=1,
        )

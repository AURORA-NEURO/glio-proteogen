"""Independent rank evidence for the four fixed GBM source signatures."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

_AXIS_COUNT: Final = 4
_SOURCE_SIGNATURE_SIZE: Final = 150


@dataclass(frozen=True, slots=True)
class RankStatistic:
    u_statistic: float
    rank_biserial: float
    tie_correction: float
    target_count: int
    background_count: int


@dataclass(frozen=True, slots=True)
class PermutationRankResult:
    statistics: tuple[RankStatistic, RankStatistic, RankStatistic, RankStatistic]
    p_values: tuple[float, float, float, float]
    q_values: tuple[float, float, float, float]
    null_standard_deviations: tuple[float, float, float, float]
    replicates: int


def average_ranks(values: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Return zero-based average ranks with deterministic exact-tie handling."""

    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("rank values must be a finite one-dimensional array")
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=np.float64)
    cursor = 0
    while cursor < len(values):
        end = cursor + 1
        while end < len(values) and values[order[end]] == values[order[cursor]]:
            end += 1
        average = (cursor + end - 1) / 2.0
        ranks[order[cursor:end]] = average
        cursor = end
    return ranks


def rank_statistic_from_ranks(
    ranks: npt.NDArray[np.float64],
    target: npt.NDArray[np.bool_],
    *,
    tie_correction: float = 1.0,
) -> RankStatistic:
    """Compute tie-corrected Mann-Whitney U and rank-biserial effect."""

    if ranks.ndim != 1 or target.ndim != 1 or ranks.shape != target.shape:
        raise ValueError("rank statistic arrays must be aligned one-dimensional vectors")
    if not np.all(np.isfinite(ranks)):
        raise ValueError("rank vector must be finite")
    if not math.isfinite(tie_correction) or not 0.0 < tie_correction <= 1.0:
        raise ValueError("tie correction must be a finite probability")
    target_count = int(np.count_nonzero(target))
    background_count = len(target) - target_count
    if target_count == 0 or background_count == 0:
        raise ValueError("rank comparison requires target and background observations")
    target_rank_sum = float(np.sum(ranks[target]))
    u_statistic = target_rank_sum - target_count * (target_count - 1) / 2.0
    denominator = target_count * background_count
    rank_biserial = 2.0 * u_statistic / denominator - 1.0
    return RankStatistic(
        u_statistic=u_statistic,
        rank_biserial=min(max(rank_biserial, -1.0), 1.0),
        tie_correction=tie_correction,
        target_count=target_count,
        background_count=background_count,
    )


def mann_whitney_rank_statistic(
    values: npt.NDArray[np.float64],
    target: npt.NDArray[np.bool_],
) -> RankStatistic:
    ranks = average_ranks(values)
    if len(values) <= 1:
        correction = 1.0
    else:
        _, counts = np.unique(values, return_counts=True)
        numerator = float(np.sum(counts**3 - counts))
        denominator = float(len(values) ** 3 - len(values))
        correction = 1.0 - numerator / denominator
    return rank_statistic_from_ranks(ranks, target, tie_correction=correction)


def benjamini_hochberg(p_values: tuple[float, ...]) -> tuple[float, ...]:
    """Return fixed-family BH q-values with deterministic tie ordering."""

    if not p_values:
        return ()
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in p_values):
        raise ValueError("p-values must be finite probabilities")
    order = sorted(range(len(p_values)), key=lambda index: (p_values[index], index))
    adjusted = [1.0] * len(p_values)
    running = 1.0
    family_size = len(p_values)
    for reverse_position in range(family_size - 1, -1, -1):
        index = order[reverse_position]
        rank = reverse_position + 1
        running = min(running, p_values[index] * family_size / rank)
        adjusted[index] = min(running, 1.0)
    return tuple(adjusted)


def _source_rank_stratum(source_rank: int) -> int:
    if not 1 <= source_rank <= _SOURCE_SIGNATURE_SIZE:
        raise ValueError("source rank must be between one and 150")
    return min(3, (source_rank - 1) // 38)


def stratified_permutation_rank_test(
    values: npt.NDArray[np.float64],
    axis_indices: npt.NDArray[np.int64],
    source_ranks: npt.NDArray[np.int64],
    *,
    replicates: int,
    seed: int,
    cancellation: CancellationContext | None = None,
) -> PermutationRankResult:
    """Compare all axes under a joint source-rank-quartile label null.

    Axis labels are shuffled only within source-rank quartiles. This retains the
    request's exact per-quartile signature coverage while breaking association with
    measured effects. One joint label permutation supplies all four null statistics,
    and BH correction is applied to the fixed four-axis family.
    """

    if values.ndim != 1 or axis_indices.ndim != 1 or source_ranks.ndim != 1:
        raise ValueError("permutation inputs must be one-dimensional")
    if not (values.shape == axis_indices.shape == source_ranks.shape):
        raise ValueError("permutation inputs must be aligned")
    if len(values) < 2 or not np.all(np.isfinite(values)):
        raise ValueError("permutation test requires at least two finite effects")
    if np.any(axis_indices < 0) or np.any(axis_indices >= _AXIS_COUNT):
        raise ValueError("permutation axis indices are invalid")
    if replicates < 1:
        raise ValueError("permutation replicate count must be positive")
    if not 0 <= seed <= 2**64 - 1:
        raise ValueError("permutation seed is outside the NumPy domain")

    ranks = average_ranks(values)
    if len(values) <= 1:
        tie_correction = 1.0
    else:
        _, counts = np.unique(values, return_counts=True)
        tie_correction = 1.0 - float(np.sum(counts**3 - counts)) / float(
            len(values) ** 3 - len(values)
        )
    observed = tuple(
        rank_statistic_from_ranks(
            ranks,
            axis_indices == axis,
            tie_correction=tie_correction,
        )
        for axis in range(_AXIS_COUNT)
    )
    strata = np.asarray(
        [_source_rank_stratum(int(source_rank)) for source_rank in source_ranks],
        dtype=np.int64,
    )
    stratum_indices = tuple(np.flatnonzero(strata == stratum) for stratum in range(4))
    rng = np.random.default_rng(seed)
    null = np.empty((replicates, _AXIS_COUNT), dtype=np.float64)
    for replicate in range(replicates):
        if replicate % 32 == 0:
            checkpoint(cancellation)
        permuted = axis_indices.copy()
        for indices in stratum_indices:
            if len(indices) > 1:
                permuted[indices] = rng.permutation(permuted[indices])
        for axis in range(_AXIS_COUNT):
            null[replicate, axis] = rank_statistic_from_ranks(
                ranks,
                permuted == axis,
                tie_correction=tie_correction,
            ).rank_biserial

    p_values = tuple(
        float(
            (
                1
                + np.count_nonzero(
                    np.abs(null[:, axis])
                    >= abs(observed[axis].rank_biserial) - np.finfo(np.float64).eps
                )
            )
            / (replicates + 1)
        )
        for axis in range(_AXIS_COUNT)
    )
    q_values = benjamini_hochberg(p_values)
    null_standard_deviations = tuple(
        float(np.std(null[:, axis], ddof=1)) if replicates > 1 else 0.0
        for axis in range(_AXIS_COUNT)
    )
    return PermutationRankResult(
        statistics=(observed[0], observed[1], observed[2], observed[3]),
        p_values=(p_values[0], p_values[1], p_values[2], p_values[3]),
        q_values=(q_values[0], q_values[1], q_values[2], q_values[3]),
        null_standard_deviations=(
            null_standard_deviations[0],
            null_standard_deviations[1],
            null_standard_deviations[2],
            null_standard_deviations[3],
        ),
        replicates=replicates,
    )


__all__ = [
    "PermutationRankResult",
    "RankStatistic",
    "average_ranks",
    "benjamini_hochberg",
    "mann_whitney_rank_statistic",
    "rank_statistic_from_ranks",
    "stratified_permutation_rank_test",
]

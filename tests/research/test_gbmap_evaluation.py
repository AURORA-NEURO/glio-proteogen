"""Scientific oracles for GBmap held-out mismatch diagnostics."""

from __future__ import annotations

import math

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution.dm import (
    dirichlet_multinomial_log_likelihood,
)
from glio_proteogen.research.gbmap_deconvolution.errors import GbmapInputError
from glio_proteogen.research.gbmap_deconvolution.evaluation import (
    aitchison_residual,
    calibrate_unknown_mass_threshold,
    evaluate_ood_diagnostics,
    finite_sample_upper_quantile,
    known_signature_tangent_condition_number,
    normalized_dm_deviance,
    saturated_dm_probabilities,
    standardized_dm_pearson_residual,
)


def test_saturated_dm_reference_is_deterministic_and_dominates_empirical_start() -> None:
    counts = np.asarray([7, 3, 0], dtype=np.int64)
    original = counts.copy()
    concentration = 5.0
    empirical_start = (counts + 0.5) / float(np.sum(counts + 0.5))

    first = saturated_dm_probabilities(counts, concentration)
    second = saturated_dm_probabilities(counts, concentration)

    np.testing.assert_array_equal(counts, original)
    np.testing.assert_array_equal(first, second)
    assert first.dtype == np.float64
    assert not first.flags.writeable
    assert float(np.sum(first)) == pytest.approx(1.0, abs=2e-12)
    assert bool(np.all(first > 0.0))
    assert dirichlet_multinomial_log_likelihood(counts, first, concentration) >= (
        dirichlet_multinomial_log_likelihood(counts, empirical_start, concentration)
    )
    assert normalized_dm_deviance(counts, first, concentration) == pytest.approx(
        0.0,
        abs=2e-12,
    )


def test_all_mismatch_diagnostics_increase_for_a_wrong_composition() -> None:
    counts = np.asarray([700, 250, 50], dtype=np.int64)
    near = np.asarray([0.68, 0.27, 0.05], dtype=np.float64)
    wrong = np.asarray([0.10, 0.10, 0.80], dtype=np.float64)

    near_diagnostics = evaluate_ood_diagnostics(
        counts,
        near,
        concentration=100.0,
        unknown_mass=0.08,
    )
    wrong_diagnostics = evaluate_ood_diagnostics(
        counts,
        wrong,
        concentration=100.0,
        unknown_mass=0.62,
    )

    assert near_diagnostics.selected_count_depth == 1_000
    assert wrong_diagnostics.normalized_dm_deviance > near_diagnostics.normalized_dm_deviance
    assert (
        wrong_diagnostics.standardized_pearson_residual
        > near_diagnostics.standardized_pearson_residual
    )
    assert wrong_diagnostics.aitchison_residual > near_diagnostics.aitchison_residual
    assert wrong_diagnostics.unknown_mass == 0.62


def test_pearson_and_aitchison_values_match_independent_formulas() -> None:
    counts = np.asarray([8, 2], dtype=np.int64)
    fitted = np.asarray([0.7, 0.3], dtype=np.float64)
    concentration = 4.0
    total = 10
    variance = (
        total * fitted * (1.0 - fitted) * (total + concentration) / (1.0 + concentration) + 1.0
    )
    expected_pearson = math.sqrt(float(np.mean(((counts - total * fitted) ** 2) / variance)))
    smoothed = (counts + 0.5) / (total + counts.size * 0.5)
    log_ratio = np.log(smoothed) - np.log(fitted)
    expected_aitchison = math.sqrt(float(np.mean((log_ratio - np.mean(log_ratio)) ** 2)))

    assert standardized_dm_pearson_residual(counts, fitted, concentration) == pytest.approx(
        expected_pearson,
        abs=2e-15,
    )
    assert aitchison_residual(counts, fitted) == pytest.approx(expected_aitchison, abs=2e-15)


def test_finite_sample_quantile_uses_the_conservative_conformal_rank() -> None:
    values = np.asarray([0.3, 0.1, 0.4, 0.2], dtype=np.float64)

    assert finite_sample_upper_quantile(values, 0.50) == 0.3
    assert finite_sample_upper_quantile(values, 0.80) == 0.4
    assert finite_sample_upper_quantile(values, 0.99) == 0.4


def test_dm_curvature_condition_number_rejects_collinear_known_signatures() -> None:
    counts = np.asarray([600, 300, 100], dtype=np.int64)
    fitted = np.asarray([0.58, 0.31, 0.11], dtype=np.float64)
    separated = np.asarray(
        [
            [0.70, 0.10, 0.20],
            [0.20, 0.70, 0.20],
            [0.10, 0.20, 0.60],
        ],
        dtype=np.float64,
    )
    duplicated = separated[:, [0, 0, 2]]

    condition = known_signature_tangent_condition_number(
        counts,
        fitted,
        separated,
        100.0,
    )
    assert math.isfinite(condition)
    assert condition >= 1.0
    assert known_signature_tangent_condition_number(counts, fitted, duplicated, 100.0) == math.inf


def test_unknown_mass_calibration_reports_hard_ceiling_effects() -> None:
    calibration = calibrate_unknown_mass_threshold(
        np.asarray([0.01, 0.02, 0.03, 0.04, 0.05], dtype=np.float64),
        np.asarray([0.20, 0.40, 0.60], dtype=np.float64),
    )
    assert calibration.threshold == 0.05
    assert calibration.achieved_specificity == 1.0
    assert calibration.omitted_family_sensitivity == 1.0
    assert calibration.hard_ceiling_preserves_specificity

    clipped = calibrate_unknown_mass_threshold(
        np.asarray([0.10, 0.20, 0.40, 0.50], dtype=np.float64),
        np.asarray([0.60, 0.70], dtype=np.float64),
        target_specificity=0.75,
        hard_ceiling=0.35,
    )
    assert clipped.finite_sample_candidate == 0.50
    assert clipped.threshold == 0.35
    assert clipped.achieved_specificity == 0.50
    assert clipped.omitted_family_sensitivity == 1.0
    assert not clipped.hard_ceiling_preserves_specificity


@pytest.mark.parametrize(
    ("counts", "probabilities", "message"),
    [
        ([True, 1], [0.5, 0.5], "exact"),
        ([0, 0], [0.5, 0.5], "positive count depth"),
        ([1, -1], [0.5, 0.5], "non-negative"),
        ([1, 1], [0.4, 0.4], "sum to one"),
        ([1, 1], [1.0, 0.0], "strictly positive"),
    ],
)
def test_diagnostics_reject_invalid_count_and_probability_semantics(
    counts: list[int | bool],
    probabilities: list[float],
    message: str,
) -> None:
    with pytest.raises(GbmapInputError, match=message):
        normalized_dm_deviance(counts, probabilities, 5.0)


def test_calibration_rejects_nonfinite_or_out_of_range_values() -> None:
    with pytest.raises(GbmapInputError, match="unit interval"):
        calibrate_unknown_mass_threshold([0.1, math.nan], [0.5])
    with pytest.raises(GbmapInputError, match="unit interval"):
        calibrate_unknown_mass_threshold([0.1], [1.1])
    with pytest.raises(GbmapInputError, match="coverage"):
        finite_sample_upper_quantile([0.1], 1.0)

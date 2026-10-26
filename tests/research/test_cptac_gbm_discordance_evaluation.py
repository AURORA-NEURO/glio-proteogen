"""Mathematical diagnostic oracles; all arrays here are explicit test fixtures."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, asdict, replace
from math import sqrt

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import evaluation
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.model import (
    DiscordanceFitConfiguration,
    fit_transcript_protein_discordance_gene,
)


@pytest.fixture(scope="module")
def arrays():
    rng = np.random.default_rng(204)
    cnv = rng.normal(size=96)
    rna = rng.normal(size=96)
    protein = 2.0 * rna + 0.4 * cnv + rng.normal(scale=0.05, size=96)
    folds = np.resize(np.arange(5, dtype=np.int8), 96)
    return cnv, rna, protein, folds


@pytest.fixture(scope="module")
def accepted_fit(arrays):
    fit = fit_transcript_protein_discordance_gene(
        *arrays,
        request_digest="sha256:" + "1" * 64,
        configuration=DiscordanceFitConfiguration(bootstrap_replicates=16),
    )
    assert fit is not None
    return fit


def test_standardized_design_orthogonal_rational_oracle():
    cnv = np.tile(np.array([-1.0, -1.0, 1.0, 1.0]), 2)
    rna = np.tile(np.array([-1.0, 1.0, -1.0, 1.0]), 2)
    design = evaluation._design(cnv, rna)
    assert design.rank == design.columns == 3
    assert design.condition_number == pytest.approx(sqrt(8.0 / 7.0))
    assert design.residual_rna_fraction == pytest.approx(1.0)
    assert design.cnv_rna_correlation == 0.0
    assert design.numerically_identified
    assert design.reasons == ()


def test_design_metrics_are_invariant_to_predictor_units_and_offsets():
    cnv = np.tile(np.array([-1.0, -1.0, 1.0, 1.0]), 2)
    rna = np.tile(np.array([-1.0, 1.0, -1.0, 1.0]), 2)
    before = evaluation._design(cnv, rna)
    after = evaluation._design(5.0 * cnv + 20.0, 0.003 * rna - 2.0)
    assert before.rank == after.rank
    assert before.condition_number == pytest.approx(after.condition_number)
    assert before.residual_rna_fraction == pytest.approx(after.residual_rna_fraction)


def test_exact_collinearity_is_exposed_even_when_ridge_point_fit_converges():
    cnv = np.resize(np.arange(-2.0, 3.0), 96)
    rna = 2.0 * cnv
    protein = 3.0 * rna + np.sin(np.arange(96)) * 0.01
    folds = np.resize(np.arange(5, dtype=np.int8), 96)
    result = evaluation.evaluate_gene_inputs(cnv, rna, protein, folds)
    assert result.point_fit_accepted
    assert result.valid_point_fold_count == 5
    assert result.conditional_design_unidentified
    assert not result.conditional_effect_reportable
    for fold in result.folds:
        assert fold.full_converged
        assert fold.conditional_design.rank == 2
        assert fold.conditional_design.condition_number is None
        assert fold.conditional_design.residual_rna_fraction < 1e-20
        assert not fold.conditional_design.numerically_identified


@pytest.mark.parametrize("noise", [1e-5, 1e-7])
def test_near_collinearity_does_not_hide_behind_nonzero_numerical_rank(noise):
    cnv = np.tile(np.array([-1.0, -1.0, 1.0, 1.0]), 2)
    orthogonal = np.tile(np.array([-1.0, 1.0, -1.0, 1.0]), 2)
    design = evaluation._design(cnv, cnv + noise * orthogonal)
    assert design.rank == 3
    assert design.residual_rna_fraction == pytest.approx(noise**2 / (1.0 + noise**2), rel=1e-5)
    assert not design.numerically_identified
    assert any("one millionth" in reason for reason in design.reasons)
    if noise < 1e-6:
        assert design.condition_number > evaluation.CONDITION_NUMBER_CEILING
        assert any("condition number" in reason for reason in design.reasons)


def test_constant_predictors_and_too_few_training_rows_have_explicit_diagnostics():
    constant_rna = evaluation._design(np.arange(8, dtype=float), np.zeros(8))
    assert constant_rna.rank == 2
    assert constant_rna.residual_rna_fraction is None
    assert constant_rna.cnv_rna_correlation is None
    assert any("RNA has no" in reason for reason in constant_rna.reasons)
    constant_cnv = evaluation._design(np.zeros(8), np.arange(8, dtype=float))
    assert constant_cnv.rank == 2
    assert constant_cnv.residual_rna_fraction == pytest.approx(1.0)
    assert evaluation._design(np.zeros(2), np.zeros(2)) is None


def test_oof_calibration_and_residual_association_have_independent_oracle():
    prediction = np.array([1.0, 2.0, 3.0])
    truth = np.array([3.0, 5.0, 7.0])
    baseline = np.zeros(3)
    rna = prediction.copy()
    cnv = -prediction
    metric = evaluation._metrics(truth, prediction, baseline, rna, cnv)
    # residual=(2,3,4), SSE=29, null SSE=83, mean absolute error=3.
    assert metric.observed_count == 3
    assert metric.mae == 3.0
    assert metric.rmse == pytest.approx(sqrt(29.0 / 3.0))
    assert metric.r2_vs_fold_train_median == pytest.approx(1.0 - 29.0 / 83.0)
    assert metric.calibration_intercept == pytest.approx(1.0)
    assert metric.calibration_slope == pytest.approx(2.0)
    assert metric.residual_mad == pytest.approx(1.4826)
    assert metric.pearson == pytest.approx(1.0)
    assert metric.residual_rna_correlation == pytest.approx(1.0)
    assert metric.residual_cnv_correlation == pytest.approx(-1.0)


def test_constant_prediction_or_truth_withholds_unidentified_calibration():
    values = np.ones(4)
    metric = evaluation._metrics(values, values, values, values, values)
    assert metric.r2_vs_fold_train_median is None
    assert metric.calibration_intercept is None
    assert metric.calibration_slope is None
    assert metric.pearson is None
    assert metric.residual_rna_correlation is None
    assert metric.residual_cnv_correlation is None
    assert evaluation._metrics(values[:2], values[:2], values[:2], values[:2], values[:2]) is None
    assert evaluation._correlation(values[:2], values[:2]) is None


def test_joint_missingness_patterns_are_complete_without_imputation(arrays):
    cnv, rna, protein, folds = (value.copy() for value in arrays)
    for pattern in range(1, 8):
        for values, bit in ((cnv, 4), (rna, 2), (protein, 1)):
            if pattern & bit:
                values[pattern] = np.nan
    result = evaluation.evaluate_gene_inputs(cnv, rna, protein, folds)
    assert result.total_count == 96
    assert result.complete_count == 89
    assert result.missing_cnv_count == result.missing_rna_count == result.missing_protein_count == 4
    assert [pattern.count for pattern in result.missingness_patterns] == [89, 1, 1, 1, 1, 1, 1, 1]
    assert sum(pattern.count for pattern in result.missingness_patterns) == 96
    assert all(fold.training_complete + fold.held_out_complete == 89 for fold in result.folds)
    assert result.common_oof_count <= 89


def test_missing_training_or_held_out_support_explains_abstention(arrays):
    cnv, rna, protein, folds = (value.copy() for value in arrays)
    rna[10:] = np.nan
    result = evaluation.evaluate_gene_inputs(cnv, rna, protein, folds)
    assert not result.point_fit_accepted
    assert result.common_oof_count == 0
    assert result.full_model is None
    assert result.conditional_design_unidentified
    assert all(
        fold.failure_reason == "insufficient training complete cases" for fold in result.folds
    )
    rna = arrays[1].copy()
    rna[folds == 0] = np.nan
    result = evaluation.evaluate_gene_inputs(cnv, rna, protein, folds)
    assert result.folds[0].failure_reason == "insufficient held-out complete cases"
    assert result.folds[0].held_out_complete == 0


def test_constant_response_is_a_point_failure_instead_of_a_numeric_effect(arrays):
    cnv, rna, _protein, folds = arrays
    result = evaluation.evaluate_gene_inputs(cnv, rna, np.ones(96), folds)
    assert not result.point_fit_accepted
    assert all(
        fold.failure_reason == "one or more fold models were numerically unidentified"
        for fold in result.folds
    )
    assert result.full_model is None
    assert not result.conditional_effect_reportable


def test_supplied_bootstrap_fit_exactly_matches_point_reconstruction(arrays, accepted_fit):
    result = evaluation.evaluate_gene_inputs(*arrays, fit=accepted_fit)
    assert result.bootstrap_fit_supplied
    assert result.supplied_fit_point_agreement is True
    assert result.point_fit_accepted
    assert result.conditional_effect_reportable
    assert not result.conditional_design_unidentified
    assert result.common_oof_count == accepted_fit.summary.oof_patient_groups
    assert result.full_model.mae == pytest.approx(accepted_fit.summary.full_model.mae, abs=1e-8)
    assert result.full_model.r2_vs_fold_train_median == pytest.approx(
        accepted_fit.summary.full_model.r2_vs_fold_train_median, abs=1e-8
    )
    assert result.delta_r2_vs_cnv_only == pytest.approx(
        accepted_fit.summary.delta_r2_vs_cnv_only, abs=2e-8
    )
    assert result.delta_r2_vs_rna_only == pytest.approx(
        accepted_fit.summary.delta_r2_vs_rna_only, abs=2e-8
    )


def test_mismatched_point_replay_cannot_make_conditional_effect_reportable(arrays, accepted_fit):
    cnv, rna, protein, folds = arrays
    changed = protein.copy()
    changed[0] += 0.1
    result = evaluation.evaluate_gene_inputs(cnv, rna, changed, folds, fit=accepted_fit)
    assert result.supplied_fit_point_agreement is False
    assert not result.conditional_effect_reportable


def test_aggregate_output_is_json_safe_frozen_and_permutation_stable(arrays, accepted_fit):
    result = evaluation.evaluate_gene_inputs(*arrays, fit=accepted_fit)
    serialized = json.dumps(asdict(result), allow_nan=False)
    assert "observed_protein" not in serialized
    assert "full_model_residual" not in serialized
    assert "patient_identifier" not in serialized
    with pytest.raises(FrozenInstanceError):
        result.complete_count = 0
    order = np.random.default_rng(7).permutation(96)
    permuted = evaluation.evaluate_gene_inputs(*(values[order] for values in arrays))
    nofit = evaluation.evaluate_gene_inputs(*arrays)
    assert asdict(permuted) == asdict(nofit)


@pytest.mark.parametrize(
    ("index", "replacement", "error"),
    [
        (0, [1.0] * 96, TypeError),
        (0, np.ones(96, dtype=np.int64), TypeError),
        (0, np.ones((96, 1)), ValueError),
        (0, np.full(96, np.inf), ValueError),
        (0, np.full(96, evaluation.MAX_ABSOLUTE_INPUT + 1), ValueError),
        (0, np.ones(95), ValueError),
        (3, np.ones(96, dtype=np.int64), TypeError),
        (3, np.zeros(96, dtype=np.int8), ValueError),
    ],
)
def test_malformed_input_arrays_fail_before_scientific_diagnostics(
    arrays, index, replacement, error
):
    inputs = list(arrays)
    inputs[index] = replacement
    with pytest.raises(error):
        evaluation.evaluate_gene_inputs(*inputs)


def test_fold_size_and_supplied_fit_type_or_alignment_are_checked(arrays, accepted_fit):
    with pytest.raises(ValueError, match="size"):
        evaluation.evaluate_gene_inputs(
            np.ones(4), np.ones(4), np.ones(4), np.arange(4, dtype=np.int8)
        )
    values = np.ones(10_001)
    with pytest.raises(ValueError, match="size"):
        evaluation.evaluate_gene_inputs(
            values, values, values, np.resize(np.arange(5, dtype=np.int8), len(values))
        )
    with pytest.raises(TypeError, match="exact development"):
        evaluation.evaluate_gene_inputs(*arrays, fit=object())
    with pytest.raises(ValueError, match="cohort size"):
        evaluation.evaluate_gene_inputs(*(values[:-1] for values in arrays), fit=accepted_fit)


def test_nonconverged_point_fits_are_reported_without_guessing_bootstrap_failure(
    arrays, monkeypatch
):
    original = evaluation.fit_huber

    def not_converged(x, y):
        fit = original(x, y)
        return None if fit is None else replace(fit, converged=False)

    monkeypatch.setattr(evaluation, "fit_huber", not_converged)
    result = evaluation.evaluate_gene_inputs(*arrays)
    assert all(
        fold.failure_reason == "one or more fold models did not converge" for fold in result.folds
    )
    assert result.bootstrap_fit_supplied is False
    assert result.supplied_fit_point_agreement is None
    assert not result.conditional_effect_reportable

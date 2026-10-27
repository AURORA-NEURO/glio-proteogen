"""Matched-support and legacy parity oracles for the numerical continuation audit."""

from __future__ import annotations

import json
import pickle
from dataclasses import FrozenInstanceError, asdict
from math import sqrt

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_cis_dosage.model import RobustFit
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    convergence_audit as audit,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import model as legacy


@pytest.fixture(scope="module")
def arrays():
    rng = np.random.default_rng(204)
    cnv, rna = rng.normal(size=96), rng.normal(size=96)
    protein = 2.0 * rna + 0.4 * cnv + rng.normal(scale=0.05, size=96)
    folds = np.resize(np.arange(5, dtype=np.int8), 96)
    return cnv, rna, protein, folds


def test_thirty_iteration_point_replay_matches_exact_legacy_crossfit_in_supplied_order(arrays):
    order = np.random.default_rng(6).permutation(96)
    cnv, rna, protein, folds = (values[order] for values in arrays)
    original = legacy._cross_fit(cnv, rna, protein, folds, legacy.DiscordanceFitConfiguration())
    assert original is not None
    replay = audit.refit_point_with_budget(cnv, rna, protein, folds, max_iterations=30)
    assert replay.accepted
    assert replay.fold_trace == original.trace
    assert replay.raw_slopes == original.slopes
    np.testing.assert_array_equal(replay.observed, original.observed)
    for values, expected in zip(
        replay.predictions,
        (original.full, original.rna_only, original.cnv_only, original.null),
        strict=True,
    ):
        np.testing.assert_array_equal(values, expected)


def test_public_budget_audit_has_exact_same_baseline_fold_receipts(arrays):
    result = audit.evaluate_convergence_budgets(*arrays)
    assert result.compared_budgets == (30, 60, 120, 240)
    assert result.legacy_30_fold_replay_agreement
    assert result.legacy_30_point_fit_accepted
    assert result.common_oof_count >= 60
    assert result.comparison_status == "matched_support_sufficient"
    assert all(budget.common_oof_count == result.common_oof_count for budget in result.budgets)
    for budget in result.budgets:
        assert {
            metric.observed_count
            for metric in (
                budget.full_model,
                budget.rna_only,
                budget.cnv_only,
                budget.training_median,
            )
        } == {result.common_oof_count}


def fake_solver_for_blocked_legacy_folds(blocked):
    """Make admission differ by cap while predictions remain exactly unchanged."""

    def fit(x, _y, *, max_iterations):
        rejected = False
        if max_iterations == 30 and x.shape[1] == 2:
            held_out_folds = set(range(5)).difference(np.asarray(x[:, 1], dtype=int) % 5)
            rejected = bool(held_out_folds.intersection(blocked))
        return RobustFit(
            x_center=np.zeros(x.shape[1]),
            x_scale=np.ones(x.shape[1]),
            y_center=0.0,
            y_scale=1.0,
            beta=np.zeros(x.shape[1] + 1),
            converged=not rejected,
            iterations=max_iterations if rejected else 1,
        )

    return fit


@pytest.mark.parametrize("blocked", [{0}, {0, 1}])
def test_recovered_folds_never_change_comparison_support(monkeypatch, blocked):
    cnv = np.arange(96, dtype=float)
    rna = np.random.default_rng(3).normal(size=96)
    protein = np.arange(96, dtype=float) + 1.0
    folds = np.resize(np.arange(5, dtype=np.int8), 96)
    # Excluded folds deliberately have extreme response values. Comparing each
    # cap on its own accepted rows would change apparent error unfairly.
    protein[np.isin(folds, list(blocked))] += 1000.0
    monkeypatch.setattr(
        audit, "fit_huber_with_budget", fake_solver_for_blocked_legacy_folds(blocked)
    )
    result = audit.evaluate_convergence_budgets(cnv, rna, protein, folds)
    expected_support = ~np.isin(folds, list(blocked))
    expected_count = int(expected_support.sum())
    assert result.common_accepted_folds == tuple(fold for fold in range(5) if fold not in blocked)
    assert result.common_oof_count == expected_count
    assert result.budgets[0].accepted_fold_count == 5 - len(blocked)
    assert result.budgets[0].accepted_oof_count == expected_count
    assert result.budgets[0].full_iteration_cap_exhausted_count == len(blocked)
    assert [budget.accepted_oof_count for budget in result.budgets[1:]] == [96, 96, 96]
    assert all(budget.common_oof_count == expected_count for budget in result.budgets)
    assert all(budget.full_model.observed_count == expected_count for budget in result.budgets)
    assert all(
        budget.full_model.mae == pytest.approx(float(np.mean(np.abs(protein[expected_support]))))
        for budget in result.budgets
    )
    assert all(
        budget.training_median == result.budgets[0].training_median for budget in result.budgets
    )
    expected_status = (
        "matched_support_sufficient"
        if len(blocked) == 1
        else "descriptive_insufficient_common_support"
    )
    assert result.comparison_status == expected_status
    assert not result.promotes_legacy_artifact
    assert not result.provides_new_bootstrap_evidence


def test_insufficient_coverage_has_true_baseline_parity_and_explicit_common_abstention(arrays):
    cnv, rna, protein, folds = (values.copy() for values in arrays)
    rna[10:] = np.nan
    result = audit.evaluate_convergence_budgets(cnv, rna, protein, folds)
    assert result.legacy_30_fold_replay_agreement
    assert not result.legacy_30_point_fit_accepted
    assert result.common_oof_count == 0
    assert result.common_accepted_folds == ()
    assert result.comparison_status == "descriptive_insufficient_common_support"
    for budget in result.budgets:
        assert budget.full_model is None
        assert budget.rna_only is None
        assert budget.cnv_only is None
        assert budget.training_median is None
        assert budget.full_iteration_cap_exhausted_count == 0
        assert all(
            trace.failure_reason == "insufficient training complete cases"
            for trace in budget.fold_trace
        )


def test_matched_error_metrics_have_hand_derived_oracle():
    result = audit._matched_metrics(
        np.array([3.0, 5.0, 7.0]), np.array([1.0, 2.0, 3.0]), np.zeros(3)
    )
    assert result.observed_count == 3
    assert result.mae == 3.0
    assert result.rmse == pytest.approx(sqrt(29.0 / 3.0))
    assert result.r2_vs_fold_train_median == pytest.approx(1.0 - 29.0 / 83.0)
    assert audit._matched_metrics(np.zeros(2), np.zeros(2), np.zeros(2)) is None
    assert (
        audit._matched_metrics(np.ones(3), np.ones(3), np.ones(3)).r2_vs_fold_train_median is None
    )


def test_missing_heldout_and_constant_assay_failures_are_retained(arrays):
    cnv, rna, protein, folds = (values.copy() for values in arrays)
    rna[folds == 0] = np.nan
    point = audit.refit_point_with_budget(cnv, rna, protein, folds, max_iterations=240)
    assert point.fold_trace[0].failure_reason == "insufficient held-out complete cases"
    constant = audit.refit_point_with_budget(np.zeros(96), rna, protein, folds, max_iterations=240)
    assert any(
        trace.failure_reason == "one or more fold models were numerically unidentified"
        for trace in constant.fold_trace
    )


def test_aggregate_audit_is_frozen_json_safe_and_joint_permutation_invariant(arrays):
    result = audit.evaluate_convergence_budgets(*arrays)
    serialized = json.dumps(asdict(result), allow_nan=False)
    assert "observed_protein" not in serialized
    assert "predictions" not in serialized
    assert "raw_slopes" not in serialized
    assert result.promotes_legacy_artifact is False
    assert result.provides_new_bootstrap_evidence is False
    with pytest.raises(FrozenInstanceError):
        result.common_oof_count = 100
    permutation = np.random.default_rng(99).permutation(96)
    changed = audit.evaluate_convergence_budgets(*(values[permutation] for values in arrays))
    assert asdict(changed) == asdict(result)


def test_development_point_arrays_are_immutable_hidden_and_nonpickleable(arrays):
    result = audit.refit_point_with_budget(*arrays, max_iterations=30)
    assert "array(" not in repr(result)
    for values in (result.observed, *result.predictions):
        assert not values.flags.writeable
        with pytest.raises(ValueError):
            values.setflags(write=True)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(result)
    with pytest.raises(TypeError, match="cannot be serialized"):
        result.__getstate__()


@pytest.mark.parametrize(
    ("budget", "error"),
    [
        (True, TypeError),
        (30.0, TypeError),
        (np.int64(30), TypeError),
        (0, ValueError),
        (31, ValueError),
        (241, ValueError),
    ],
)
def test_point_refitter_rejects_undeclared_or_coerced_budgets(arrays, budget, error):
    with pytest.raises(error):
        audit.refit_point_with_budget(*arrays, max_iterations=budget)


@pytest.mark.parametrize(
    ("index", "replacement", "error"),
    [
        (0, [1.0] * 96, TypeError),
        (0, np.ones(96, dtype=int), TypeError),
        (0, np.ones((96, 1)), ValueError),
        (0, np.full(96, np.inf), ValueError),
        (0, np.full(96, audit.MAX_ABSOLUTE_INPUT + 1.0), ValueError),
        (0, np.ones(95), ValueError),
        (3, np.arange(96, dtype=int), TypeError),
        (3, np.zeros(96, dtype=np.int8), ValueError),
    ],
)
def test_development_refitter_validates_arrays_without_borrowing_mutable_inputs(
    arrays, index, replacement, error
):
    values = list(arrays)
    values[index] = replacement
    with pytest.raises(error):
        audit.refit_point_with_budget(*values, max_iterations=30)


def test_small_or_excessive_cohort_sizes_are_rejected():
    with pytest.raises(ValueError, match="size"):
        audit.refit_point_with_budget(
            np.zeros(4), np.zeros(4), np.zeros(4), np.arange(4, dtype=np.int8), max_iterations=30
        )
    large = np.zeros(10_001)
    with pytest.raises(ValueError, match="size"):
        audit.refit_point_with_budget(
            large,
            large,
            large,
            np.resize(np.arange(5, dtype=np.int8), len(large)),
            max_iterations=30,
        )

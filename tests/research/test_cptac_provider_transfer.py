"""Independent synthetic source-policy, loss and paired-bootstrap oracles."""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import FrozenInstanceError, asdict, replace
from math import ceil, sqrt

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_external_admission import transfer
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    nested_selection as nested,
)

DIGEST = "sha256:" + "a" * 64
ORDER = ("training_median", "rna_only", "cnv_only", "full")


@pytest.fixture(scope="module")
def arrays():
    rng = np.random.default_rng(271828)
    cnv, rna = rng.normal(size=72), rng.normal(size=72)
    protein = 2.0 * rna + 0.4 * cnv + rng.normal(scale=0.05, size=72)
    folds = transfer.deterministic_patient_folds(tuple(f"PRIVATE-CASE-{i:03}" for i in range(72)))
    return cnv, rna, protein, folds


@pytest.fixture(scope="module")
def source(arrays):
    result = transfer.fit_source_gene(*arrays)
    assert result.receipt.accepted, result.receipt.failure_reason
    return result


@pytest.fixture(scope="module")
def point(arrays):
    result = nested.nested_point_fit(*arrays)
    assert result.accepted
    return result


@pytest.fixture
def arithmetic_source(source):
    """Known synthetic predictors: median2, RNA, CNV, and RNA+CNV."""
    predictors = (
        transfer._FrozenPredictor("training_median", 2.0, (), (), (), 0.0, 1.0),
        transfer._FrozenPredictor("rna_only", None, (0.0,), (1.0,), (0.0, 1.0), 0.0, 1.0),
        transfer._FrozenPredictor("cnv_only", None, (0.0,), (1.0,), (0.0, 1.0), 0.0, 1.0),
        transfer._FrozenPredictor("full", None, (0.0, 0.0), (1.0, 1.0), (0.0, 1.0, 1.0), 0.0, 1.0),
    )
    return replace(
        source,
        receipt=replace(source.receipt, selected_candidate="rna_only"),
        _predictors=predictors,
    )


@pytest.fixture
def external():
    return (
        np.tile([0.0, 1.0, 2.0, 3.0], 12),
        np.tile([0.0, 2.0, 4.0, 6.0], 12),
        np.tile([1.0, 3.0, 7.0, 9.0], 12),
    )


def test_source_fold_assignment_has_an_independent_hash_oracle_and_is_order_equivariant():
    keys = tuple(f"PRIVATE-CASE-{index:03}" for index in range(72))
    expected = {
        key: rank % 5
        for rank, key in enumerate(
            sorted(keys, key=lambda key: (hashlib.sha256(key.encode("utf-8")).digest(), key))
        )
    }
    folds = transfer.deterministic_patient_folds(keys)
    assert folds.dtype == np.int8
    assert {key: int(fold) for key, fold in zip(keys, folds, strict=True)} == expected
    assert sorted(np.bincount(folds).tolist()) == [14, 14, 14, 15, 15]
    reversed_folds = transfer.deterministic_patient_folds(tuple(reversed(keys)))
    assert np.array_equal(reversed_folds[::-1], folds)
    with pytest.raises(ValueError):
        folds.setflags(write=True)
    with pytest.raises(ValueError):
        folds[0] = 99


@pytest.mark.parametrize(
    "keys",
    [
        (),
        tuple(str(i) for i in range(59)),
        tuple(str(i) for i in range(10001)),
        [str(i) for i in range(72)],
        ("REPEATED",) * 72,
    ],
)
def test_source_fold_inventory_is_bounded_unique_and_exact_tuple(keys):
    with pytest.raises(ValueError):
        transfer.deterministic_patient_folds(keys)


@pytest.mark.parametrize(
    "bad", ["", " ", "A B", "A\tB", "A\x00B", "A\x7fB", "é", "X" * 257, 7, None]
)
def test_source_fold_keys_are_sanitized_without_echo(bad):
    keys = (bad, *(f"PRIVATE-{i}" for i in range(71)))
    with pytest.raises(ValueError) as error:
        transfer.deterministic_patient_folds(keys)
    assert "PRIVATE-" not in str(error.value)


def test_source_fit_requires_all_families_all_source_cases_and_five_folds(source):
    receipt = source.receipt
    assert receipt.accepted and receipt.failure_reason is None
    assert receipt.complete_count == receipt.common_oof_count == 72
    assert receipt.valid_outer_folds == 5
    assert tuple(item.candidate for item in receipt.selection_evidence) == ORDER
    assert all(item.eligible and item.source_oof_count == 72 for item in receipt.selection_evidence)
    assert tuple(item.candidate for item in source._predictors) == ORDER
    assert tuple(item.candidate for item in receipt.final_fits) == ORDER
    assert all(item.available and item.failure_reason is None for item in receipt.final_fits)
    assert receipt.final_fit_iterations[0] is None
    assert all(1 <= value <= 240 for value in receipt.final_fit_iterations[1:])
    winner = min(
        receipt.selection_evidence,
        key=lambda item: (item.source_oof_mae, ORDER.index(item.candidate)),
    )
    assert receipt.selected_candidate == winner.candidate
    for trace in receipt.fold_trace:
        assert trace.comparison_accepted
        assert trace.training_complete >= 48 and trace.held_out_complete >= 3
        assert len(trace.candidates) == 4
        assert all(
            item.inner_oof_count == trace.training_complete
            for item in trace.candidates
            if item.eligible
        )


def test_source_heldout_labels_do_not_enter_that_folds_inner_selection(arrays, source):
    cnv, rna, protein, folds = arrays
    poisoned = protein.copy()
    poisoned[folds == 0] += 1e5
    changed = transfer.fit_source_gene(cnv, rna, poisoned, folds)
    original_trace = source.receipt.fold_trace[0]
    changed_trace = changed.receipt.fold_trace[0]
    assert changed_trace.candidates == original_trace.candidates
    assert changed_trace.selected_candidate == original_trace.selected_candidate
    assert changed_trace.selection_basis == original_trace.selection_basis


@pytest.mark.parametrize(
    ("losses", "winner"),
    [
        ((0, 0, 0, 0), "training_median"),
        ((1, 0, 0, 0), "rna_only"),
        ((1, 2, 0, 0), "cnv_only"),
        ((1, 2, 3, 0), "full"),
    ],
)
def test_final_source_exact_ties_follow_the_frozen_complexity_order(
    arrays, point, monkeypatch, losses, winner
):
    truth = arrays[2]
    programmed = replace(point, fixed_predictions=tuple(truth + loss for loss in losses))
    monkeypatch.setattr(nested, "nested_point_fit", lambda *_args: programmed)
    result = transfer.fit_source_gene(*arrays)
    assert result.receipt.accepted
    assert result.receipt.selected_candidate == winner


def test_final_source_choice_pools_individual_errors_instead_of_fold_means(
    arrays, point, monkeypatch
):
    truth, folds = arrays[2:]
    rna_error = np.where(folds == 0, 2.0, 0.0)
    assert np.mean(rna_error) > 0.41
    assert np.mean([np.mean(rna_error[folds == fold]) for fold in range(5)]) < 0.41
    programmed = replace(
        point, fixed_predictions=(truth + 4, truth + rna_error, truth + 0.41, truth + 5)
    )
    monkeypatch.setattr(nested, "nested_point_fit", lambda *_args: programmed)
    result = transfer.fit_source_gene(*arrays)
    assert result.receipt.accepted
    assert result.receipt.selected_candidate == "cnv_only"


def test_mae_selection_is_not_retuned_to_squared_error(arrays, point, monkeypatch):
    truth = arrays[2]
    full_error = np.tile([0.0, 0.0, 0.0, 8.0], 18)
    assert np.mean(full_error) == 2.0 and sqrt(np.mean(full_error**2)) == 4.0
    programmed = replace(
        point, fixed_predictions=(truth + 9, truth + 8, truth + 3, truth + full_error)
    )
    monkeypatch.setattr(nested, "nested_point_fit", lambda *_args: programmed)
    result = transfer.fit_source_gene(*arrays)
    assert result.receipt.accepted
    assert result.receipt.selected_candidate == "full"


def test_stricter_final_all_five_support_can_reject_an_otherwise_accepted_nested_point(monkeypatch):
    rng = np.random.default_rng(204)
    cnv, rna = rng.normal(size=96), rng.normal(size=96)
    truth = 2 * rna + 0.4 * cnv + rng.normal(scale=0.05, size=96)
    folds = np.resize(np.arange(5, dtype=np.int8), 96)
    original = nested._fit_candidate

    def fail_one_outer(candidate, *args, **kwargs):
        if candidate == "full" and kwargs["outer_fold"] == 0 and kwargs["inner_fold"] is None:
            return nested.CandidateFit(candidate, None, None, "synthetic outer failure")
        return original(candidate, *args, **kwargs)

    monkeypatch.setattr(nested, "_fit_candidate", fail_one_outer)
    nested_point = nested.nested_point_fit(cnv, rna, truth, folds)
    assert nested_point.accepted and nested_point.common_oof_count >= 60
    result = transfer.fit_source_gene(cnv, rna, truth, folds)
    assert not result.receipt.accepted
    assert result.receipt.valid_outer_folds == 4
    assert "all-five-fold" in result.receipt.failure_reason
    assert not result.receipt.selection_evidence[-1].eligible
    assert result._predictors == () and result.receipt.final_fits == ()


def test_final_source_failure_preserves_per_family_evidence(arrays, monkeypatch):
    original = nested._fit_candidate

    def fail_final(candidate, *args, **kwargs):
        if candidate == "full" and kwargs["outer_fold"] == -1:
            return nested.CandidateFit(candidate, None, None, "synthetic240cap")
        return original(candidate, *args, **kwargs)

    monkeypatch.setattr(nested, "_fit_candidate", fail_final)
    result = transfer.fit_source_gene(*arrays)
    assert not result.receipt.accepted and result._predictors == ()
    assert result.receipt.common_oof_count == 72
    assert [item.available for item in result.receipt.final_fits] == [True, True, True, False]
    assert result.receipt.final_fits[-1].failure_reason == "synthetic240cap"


@pytest.mark.parametrize("complete_count", [0, 59])
def test_source_missingness_cannot_bypass_the_60_oof_gate(arrays, complete_count):
    cnv, rna, protein, folds = arrays
    missing = protein.copy()
    missing[complete_count:] = np.nan
    result = transfer.fit_source_gene(cnv, rna, missing, folds)
    assert result.receipt.complete_count == complete_count
    assert not result.receipt.accepted and not result._predictors
    assert result.receipt.common_oof_count <= complete_count


def test_source_exact60_complete_cases_retain48_outer_training_cases(arrays):
    cnv, rna, protein, folds = arrays
    keep = np.concatenate([np.flatnonzero(folds == fold)[:12] for fold in range(5)])
    missing = np.full(72, np.nan)
    missing[keep] = protein[keep]
    result = transfer.fit_source_gene(cnv, rna, missing, folds)
    assert result.receipt.accepted
    assert result.receipt.complete_count == result.receipt.common_oof_count == 60
    assert all(trace.training_complete == 48 for trace in result.receipt.fold_trace)
    assert all(trace.held_out_complete == 12 for trace in result.receipt.fold_trace)


def test_inner32_and_outer3_failures_are_not_mislabeled_as_model_winners(arrays):
    cnv, rna, protein, _ = arrays
    skewed_folds = np.repeat(np.arange(5, dtype=np.int8), [3, 3, 3, 3, 60])
    result = transfer.fit_source_gene(cnv, rna, protein, skewed_folds)
    assert not result.receipt.accepted
    for trace in result.receipt.fold_trace[:4]:
        assert trace.selection_basis == "fallback_inner_support"
        assert trace.selected_candidate == "training_median"
        assert all(not item.eligible and item.inner_mae is None for item in trace.candidates)
    assert result.receipt.fold_trace[4].training_complete == 12
    assert not result.receipt.fold_trace[4].comparison_accepted


@pytest.mark.parametrize("constant", ["cnv", "rna", "protein"])
def test_degenerate_required_training_scales_abstain_without_fake_perfect_fit(arrays, constant):
    values = [value.copy() for value in arrays]
    values[("cnv", "rna", "protein").index(constant)][:] = 0
    result = transfer.fit_source_gene(*values)
    assert not result.receipt.accepted and not result._predictors


def test_every_regression_call_keeps_the_frozen240_budget(arrays, monkeypatch):
    calls = []
    original = nested.fit_huber_with_budget

    def observed(*args, **kwargs):
        calls.append(kwargs["max_iterations"])
        return original(*args, **kwargs)

    monkeypatch.setattr(nested, "fit_huber_with_budget", observed)
    result = transfer.fit_source_gene(*arrays)
    assert result.receipt.accepted and calls and set(calls) == {240}


def test_external_metrics_and_primary_secondary_signs_have_hand_derived_oracles(
    arithmetic_source, external
):
    result = transfer.evaluate_external_gene(arithmetic_source, *external, request_digest=DIGEST)
    assert result.accepted
    expected = (
        (3.5, sqrt(19), 0),
        (2.0, sqrt(5), 14 / 19),
        (3.5, sqrt(16.5), 5 / 38),
        (0.5, sqrt(0.5), 37 / 38),
        (2.0, sqrt(5), 14 / 19),
    )
    assert tuple(item.candidate for item in result.point_metrics) == (*ORDER, "selected_policy")
    for metric, (mae, rmse, r2) in zip(result.point_metrics, expected, strict=True):
        assert metric.observed_count == 48
        assert metric.mae == pytest.approx(mae)
        assert metric.rmse == pytest.approx(rmse)
        assert metric.r2_vs_source_training_median == pytest.approx(r2)
    assert result.primary_full_minus_cnv_mae == -3.0
    assert result.secondary_selected_minus_full_mae == 1.5
    assert (
        result.aligned_external_validation
        is result.clinical_validation
        is result.default_promotion
        is False
    )


def test_all128_bootstrap_draws_match_an_independent_paired_error_oracle(
    arithmetic_source, external
):
    cnv, rna, truth = external
    result = transfer.evaluate_external_gene(arithmetic_source, *external, request_digest=DIGEST)
    uncertainty = result.uncertainty
    assert uncertainty is not None
    seed = int.from_bytes(
        hashlib.sha256((transfer.PROFILE_ID + ":external-paired:" + DIGEST).encode()).digest()[:8],
        "big",
    )
    assert uncertainty.seed == seed
    rng = np.random.default_rng(seed)
    predictions = (np.full(48, 2.0), rna, cnv, rna + cnv, rna)
    models = [[] for _ in predictions]
    primary, secondary = [], []
    for _ in range(128):
        draw = rng.integers(0, 48, size=48)
        baseline_sse = np.sum((truth[draw] - 2) ** 2)
        metrics = []
        for prediction, samples in zip(predictions, models, strict=True):
            error = truth[draw] - prediction[draw]
            metric = (
                float(np.mean(np.abs(error))),
                sqrt(float(np.mean(error**2))),
                1 - float(np.sum(error**2)) / baseline_sse,
            )
            samples.append(metric)
            metrics.append(metric)
        primary.append(
            float(
                np.mean(
                    np.abs(truth[draw] - predictions[3][draw])
                    - np.abs(truth[draw] - predictions[2][draw])
                )
            )
        )
        secondary.append(
            float(
                np.mean(
                    np.abs(truth[draw] - predictions[4][draw])
                    - np.abs(truth[draw] - predictions[3][draw])
                )
            )
        )

    def expected_interval(values):
        ordered = sorted(values)
        return ordered[ceil(0.05 * len(ordered)) - 1], ordered[ceil(0.95 * len(ordered)) - 1]

    for interval, samples in (
        (uncertainty.primary_full_minus_cnv_mae, primary),
        (uncertainty.secondary_selected_minus_full_mae, secondary),
    ):
        assert (interval.lower, interval.upper) == pytest.approx(expected_interval(samples))
        assert interval.confidence_level == 0.9 and interval.replicates == 128
    for intervals, samples in zip(uncertainty.metrics, models, strict=True):
        for column, interval in enumerate(
            (intervals.mae, intervals.rmse, intervals.r2_vs_source_training_median)
        ):
            assert interval is not None
            assert (interval.lower, interval.upper) == pytest.approx(
                expected_interval([sample[column] for sample in samples])
            )
    assert uncertainty.replicates_requested == uncertainty.replicates_successful == 128
    assert uncertainty.replicates_required == 103
    assert (
        uncertainty.training_refitted
        is uncertainty.selection_repeated
        is uncertainty.training_uncertainty_available
        is False
    )


def test_external_scoring_and_resampling_never_refit_or_reselect(
    arithmetic_source, external, monkeypatch
):
    before = arithmetic_source._predictors
    receipt_before = asdict(arithmetic_source.receipt)

    def forbidden(*_args, **_kwargs):
        pytest.fail("external values entered source fitting or selection")

    monkeypatch.setattr(transfer, "fit_source_gene", forbidden)
    monkeypatch.setattr(nested, "nested_point_fit", forbidden)
    monkeypatch.setattr(nested, "_fit_candidate", forbidden)
    original = transfer.evaluate_external_gene(arithmetic_source, *external, request_digest=DIGEST)
    shifted = transfer.evaluate_external_gene(
        arithmetic_source,
        external[0] * 10,
        external[1] * 20,
        external[2] + 100,
        request_digest=DIGEST,
    )
    assert original.accepted and shifted.accepted
    assert (
        arithmetic_source._predictors == before
        and asdict(arithmetic_source.receipt) == receipt_before
    )
    assert original.source.selected_candidate == shifted.source.selected_candidate
    assert original.primary_full_minus_cnv_mae != shifted.primary_full_minus_cnv_mae


def test_frozen_transform_prediction_uses_source_centers_scales_and_response_inverse(
    arithmetic_source, external
):
    frozen = replace(
        arithmetic_source._predictors[3],
        center=(5.0, 2.0),
        scale=(2.0, 4.0),
        beta=(0.5, 3.0, -2.0),
        y_center=7.0,
        y_scale=2.0,
    )
    source = replace(arithmetic_source, _predictors=(*arithmetic_source._predictors[:3], frozen))
    result = transfer.evaluate_external_gene(source, *external, request_digest=DIGEST)
    expected = 7 + 2 * (0.5 + 3 * (external[1] - 5) / 2 - 2 * (external[0] - 2) / 4)
    assert result.accepted
    assert result.point_metrics[3].mae == pytest.approx(np.mean(np.abs(external[2] - expected)))


def test_external48_is_scoring_support_and_needs_no60_oof_gate(arithmetic_source, external):
    accepted = transfer.evaluate_external_gene(arithmetic_source, *external, request_digest=DIGEST)
    assert (
        accepted.accepted
        and accepted.external_minimum == accepted.external_common_comparison_count == 48
    )
    refused = transfer.evaluate_external_gene(
        arithmetic_source, *(value[:47] for value in external), request_digest=DIGEST
    )
    assert not refused.accepted and refused.external_complete_count == 47
    assert refused.point_metrics == () and refused.uncertainty is None


def test_common_complete_support_preserves_zero_and_does_not_use_model_specific_rows(
    arithmetic_source, external
):
    arrays = [np.concatenate((value, [1.0] * 4)) for value in external]
    arrays[0][48] = np.nan
    arrays[1][49] = np.nan
    arrays[2][50:] = np.nan
    result = transfer.evaluate_external_gene(arithmetic_source, *arrays, request_digest=DIGEST)
    expected = transfer.evaluate_external_gene(arithmetic_source, *external, request_digest=DIGEST)
    assert result == expected
    assert result.accepted and result.external_complete_count == 48
    absent = transfer.evaluate_external_gene(
        arithmetic_source, external[0], external[1], np.full(48, np.nan), request_digest=DIGEST
    )
    assert (
        not absent.accepted and absent.external_complete_count == 0 and absent.point_metrics == ()
    )


@pytest.mark.parametrize("mode", ["swap", "missing", "duplicate", "unknown_selected"])
def test_counterfeit_frozen_family_order_or_membership_is_rejected(
    arithmetic_source, external, mode
):
    predictors = list(arithmetic_source._predictors)
    receipt = arithmetic_source.receipt
    if mode == "swap":
        predictors[1], predictors[2] = predictors[2], predictors[1]
    elif mode == "missing":
        predictors.pop()
    elif mode == "duplicate":
        predictors[2] = predictors[1]
    else:
        receipt = replace(receipt, selected_candidate="external_best")
    source = replace(arithmetic_source, _predictors=tuple(predictors), receipt=receipt)
    with pytest.raises(ValueError, match="predictor contract"):
        transfer.evaluate_external_gene(source, *external, request_digest=DIGEST)


def test_source_abstention_is_not_promoted_by_a_well_supported_external_cohort(source, external):
    rejected = replace(
        source,
        receipt=replace(source.receipt, accepted=False, failure_reason="source unsupported"),
        _predictors=(),
    )
    result = transfer.evaluate_external_gene(rejected, *external, request_digest=DIGEST)
    assert not result.accepted and result.failure_reason == "source unsupported"
    assert result.external_complete_count == 48 and result.external_common_comparison_count == 0
    assert result.point_metrics == ()


def test_nonfinite_prediction_causes_whole_comparison_abstention(arithmetic_source, external):
    bad = replace(arithmetic_source._predictors[3], y_scale=float("nan"))
    source = replace(arithmetic_source, _predictors=(*arithmetic_source._predictors[:3], bad))
    result = transfer.evaluate_external_gene(source, *external, request_digest=DIGEST)
    assert not result.accepted and result.external_complete_count == 48
    assert result.external_common_comparison_count == 0 and result.point_metrics == ()
    assert "no model-specific observation deletion" in result.failure_reason


def test_finite_prediction_with_overflowing_error_cannot_emit_nonfinite_metrics(
    arithmetic_source, external
):
    bad = replace(arithmetic_source._predictors[3], y_center=1e200)
    source = replace(arithmetic_source, _predictors=(*arithmetic_source._predictors[:3], bad))
    with np.errstate(over="ignore"):
        result = transfer.evaluate_external_gene(source, *external, request_digest=DIGEST)
    assert not result.accepted and result.point_metrics == () and result.uncertainty is None
    assert result.failure_reason == "non-finite external metric"


def test_undefined_r2_preserves_valid_loss_points_and_intervals(arithmetic_source, external):
    result = transfer.evaluate_external_gene(
        arithmetic_source, external[0], external[1], np.full(48, 2.0), request_digest=DIGEST
    )
    assert result.accepted and result.uncertainty is not None
    assert all(item.r2_vs_source_training_median is None for item in result.point_metrics)
    assert all(item.r2_vs_source_training_median is None for item in result.uncertainty.metrics)
    assert all(
        item.mae.replicates == item.rmse.replicates == 128 for item in result.uncertainty.metrics
    )


def test_r2_interval_requires_its_own103_valid_draws(arithmetic_source, external):
    truth = np.full(48, 2.0)
    truth[0] = 3.0
    result = transfer.evaluate_external_gene(
        arithmetic_source, external[0], external[1], truth, request_digest=DIGEST
    )
    assert result.accepted and result.uncertainty is not None
    assert all(item.r2_vs_source_training_median is not None for item in result.point_metrics)
    rng = np.random.default_rng(result.uncertainty.seed)
    valid = sum(bool(np.any(rng.integers(0, 48, size=48) == 0)) for _ in range(128))
    assert valid < 103
    assert all(item.r2_vs_source_training_median is None for item in result.uncertainty.metrics)
    assert result.uncertainty.replicates_successful == 128


@pytest.mark.parametrize(("failed_draws", "accepted"), [(25, True), (26, False)])
def test_bootstrap103_gate_counts_failed_draws_without_replacement(
    arithmetic_source, external, monkeypatch, failed_draws, accepted
):
    original = transfer._metrics
    calls = 0

    def programmed(candidate, *args):
        nonlocal calls
        calls += 1
        metric = original(candidate, *args)
        draw = (calls - 6) // 5
        if calls > 5 and 0 <= draw < failed_draws and candidate == "full":
            return replace(metric, mae=float("nan"))
        return metric

    monkeypatch.setattr(transfer, "_metrics", programmed)
    result = transfer.evaluate_external_gene(arithmetic_source, *external, request_digest=DIGEST)
    assert result.accepted is accepted
    assert calls == 5 + 5 * 128
    assert len(result.point_metrics) == 5 and result.primary_full_minus_cnv_mae == -3.0
    if accepted:
        assert result.uncertainty.replicates_successful == 103
        assert result.uncertainty.primary_full_minus_cnv_mae.replicates == 103
    else:
        assert result.uncertainty is None and "below103of128" in result.failure_reason


def test_repeated_scoring_is_deterministic_but_request_digest_changes_draw_basis(
    arithmetic_source, external
):
    first = transfer.evaluate_external_gene(arithmetic_source, *external, request_digest=DIGEST)
    repeat = transfer.evaluate_external_gene(arithmetic_source, *external, request_digest=DIGEST)
    changed = transfer.evaluate_external_gene(
        arithmetic_source, *external, request_digest="sha256:" + "b" * 64
    )
    assert first == repeat
    assert changed.point_metrics == first.point_metrics
    assert changed.uncertainty.seed != first.uncertainty.seed


@pytest.mark.parametrize("bad", [None, "", "a" * 64, "sha256:" + "G" * 64, "sha256:" + "A" * 64, 7])
def test_external_request_digest_is_canonical(arithmetic_source, external, bad):
    with pytest.raises(ValueError):
        transfer.evaluate_external_gene(arithmetic_source, *external, request_digest=bad)


@pytest.mark.parametrize("bad", [None, object(), {"accepted": True}])
def test_external_evaluation_requires_a_typed_frozen_source_fit(external, bad):
    with pytest.raises(TypeError, match="frozen source fit"):
        transfer.evaluate_external_gene(bad, *external, request_digest=DIGEST)


@pytest.mark.parametrize(
    "mode",
    [
        "list",
        "integer",
        "complex",
        "two_dimensional",
        "empty",
        "oversized",
        "inf",
        "magnitude",
        "unequal",
    ],
)
def test_external_array_contract_rejects_invalid_inputs_privately(
    arithmetic_source, external, mode
):
    values = list(external)
    if mode == "list":
        values[0] = values[0].tolist()
    elif mode == "integer":
        values[0] = values[0].astype(np.int64)
    elif mode == "complex":
        values[0] = values[0].astype(complex)
    elif mode == "two_dimensional":
        values[0] = values[0][:, None]
    elif mode == "empty":
        values[0] = np.array([], dtype=float)
    elif mode == "oversized":
        values[0] = np.zeros(10001)
    elif mode == "inf":
        values[0] = np.full(48, np.inf)
    elif mode == "magnitude":
        values[0] = np.full(48, 1e12 + 1)
    else:
        values[0] = values[0][:-1]
    with pytest.raises(TypeError if mode in ("list", "integer", "complex") else ValueError):
        transfer.evaluate_external_gene(arithmetic_source, *values, request_digest=DIGEST)


def test_private_predictors_are_frozen_hidden_nonpickleable_and_receipts_aggregate_only(
    source, external
):
    for value in (source, *source._predictors):
        with pytest.raises(TypeError):
            pickle.dumps(value)
        with pytest.raises(TypeError):
            value.__getstate__()
    with pytest.raises(FrozenInstanceError):
        source.receipt.accepted = False
    with pytest.raises(FrozenInstanceError):
        source._predictors[1].y_scale = 99
    assert "_predictors" not in repr(source)
    for predictor in source._predictors:
        assert "beta=" not in repr(predictor) and "median=" not in repr(predictor)
    result = transfer.evaluate_external_gene(source, *external, request_digest=DIGEST)
    encoded = json.dumps(asdict(result), allow_nan=False)
    assert "PRIVATE-CASE" not in encoded
    stack = [asdict(result)]
    while stack:
        item = stack.pop()
        assert not isinstance(item, np.ndarray)
        if isinstance(item, dict):
            assert not {
                "_predictors",
                "beta",
                "predictions",
                "residuals",
                "patient_keys",
                "case_submitter_id",
            }.intersection(item)
            stack.extend(item.values())
        elif isinstance(item, (tuple, list)):
            assert len(item) not in (48, 56, 72, 112, 128)
            stack.extend(item)

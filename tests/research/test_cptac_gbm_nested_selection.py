"""Numerical, bootstrap, support and provenance checks for nested selection."""

from __future__ import annotations

import json
import pickle
from dataclasses import FrozenInstanceError, asdict, replace
from math import sqrt

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    model as legacy,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    nested_selection as nested,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.profile import (
    algorithm_profile,
)

DIGEST = "sha256:" + "7" * 64


@pytest.fixture(scope="module")
def arrays():
    rng = np.random.default_rng(204)
    cnv, rna = rng.normal(size=96), rng.normal(size=96)
    protein = 2.0 * rna + 0.4 * cnv + rng.normal(scale=0.05, size=96)
    return cnv, rna, protein, np.resize(np.arange(5, dtype=np.int8), 96)


@pytest.fixture(scope="module")
def point(arrays):
    result = nested.nested_point_fit(*arrays)
    assert result.accepted
    return result


@pytest.fixture(scope="module")
def result(arrays):
    return nested.fit_nested_selection_gene(*arrays, request_digest=DIGEST)


def test_nested_selection_uses_five_untouched_outer_folds_and_all_four_inner_blocks(point):
    assert point.accepted
    assert point.complete_count == point.common_oof_count == point.selected_oof_count == 96
    for trace in point.fold_trace:
        assert trace.comparison_accepted
        assert trace.training_complete + trace.held_out_complete == 96
        assert trace.selection_basis == "inner_mae"
        assert trace.selected_candidate == "full"
        for candidate in trace.candidates:
            if candidate.eligible:
                assert candidate.inner_oof_count == trace.training_complete
                assert candidate.inner_mae is not None
                assert not candidate.failure_reasons


def test_point_reconstruction_and_paired_deltas_match_direct_oof_oracle(arrays, point):
    truth = arrays[2][point.comparison_mask]
    selected = point.selected_predictions[point.comparison_mask]
    null = point.fixed_predictions[0][point.comparison_mask]
    expected_null_sse = float(np.sum((truth - null) ** 2))
    assert point.summary.selected.mae == pytest.approx(float(np.mean(np.abs(truth - selected))))
    assert point.summary.selected.rmse == pytest.approx(
        sqrt(float(np.mean((truth - selected) ** 2)))
    )
    for index, metric in enumerate(point.summary.fixed):
        prediction = point.fixed_predictions[index][point.comparison_mask]
        expected_mae = float(np.mean(np.abs(truth - prediction)))
        expected_r2 = 1.0 - float(np.sum((truth - prediction) ** 2)) / expected_null_sse
        assert metric.observed_count == 96
        assert metric.mae == pytest.approx(expected_mae)
        assert metric.r2_vs_fold_train_median == pytest.approx(expected_r2)
        assert point.summary.deltas[index].mae_difference == pytest.approx(
            point.summary.selected.mae - expected_mae
        )
        assert point.summary.deltas[index].r2_difference == pytest.approx(
            point.summary.selected.r2_vs_fold_train_median - expected_r2
        )
    assert point.summary.fixed[0].r2_vs_fold_train_median == 0.0
    assert sum(count.fold_decisions for count in point.summary.selection_counts) == 5
    assert sum(count.comparison_observations for count in point.summary.selection_counts) == 96


def test_metric_implementation_has_a_hand_derived_oracle():
    metric = nested._metrics(
        "test", np.array([3.0, 5.0, 7.0]), np.array([1.0, 2.0, 3.0]), np.zeros(3)
    )
    assert metric.mae == 3.0
    assert metric.rmse == pytest.approx(sqrt(29.0 / 3.0))
    assert metric.r2_vs_fold_train_median == pytest.approx(1.0 - 29.0 / 83.0)
    assert nested._metrics("test", np.ones(2), np.zeros(2), np.zeros(2)) is None
    assert nested._metrics("test", np.ones(3), np.ones(3), np.ones(3)) is None


def test_inner_selection_pools_participant_errors_instead_of_averaging_fold_means(monkeypatch):
    # Four inner blocks have 24,16,12,12 observations. RNA error is 2 in the
    # largest block and zero elsewhere: pooled MAE .75, equal-block MAE .5.
    # CNV error is .6 everywhere, so only the participant-pooled rule picks CNV.
    folds = np.repeat(np.arange(1, 5, dtype=np.int8), [24, 16, 12, 12])
    cnv = folds.astype(float)
    rna = cnv.copy()
    protein = np.zeros(64)

    class ProgrammedCandidate:
        available = True
        failure_reason = None

        def __init__(self, candidate):
            self.candidate = candidate

        def predict(self, values, _rna):
            if self.candidate == "rna_only":
                return np.where(values == 1.0, 2.0, 0.0)
            return np.full(
                len(values), {"training_median": 5.0, "cnv_only": 0.6, "full": 6.0}[self.candidate]
            )

    def programmed_fit(candidate, *_arrays, **_context):
        return ProgrammedCandidate(candidate)

    monkeypatch.setattr(nested, "_fit_candidate", programmed_fit)
    result = nested._inner_select(cnv, rna, protein, folds, outer_fold=0)
    assert result.selected_candidate == "cnv_only"
    scores = {item.candidate: item.inner_mae for item in result.candidates}
    assert scores["rna_only"] == 0.75
    assert scores["cnv_only"] == pytest.approx(0.6)
    assert all(item.inner_oof_count == 64 for item in result.candidates)


def test_public_full_nested_bootstrap_returns_paired_intervals_and_honest_frequencies(result):
    assert result.profile_id == "cptac-gbm-nested-comparator-selection/1.0.0"
    assert result.accepted
    assert result.failure_reason is None
    assert result.bootstrap_requested == result.bootstrap_attempted == 128
    assert 103 <= result.bootstrap_successful <= 128
    uncertainty = result.uncertainty
    assert uncertainty is not None
    assert uncertainty.seed == legacy._bootstrap_seed(DIGEST)
    assert uncertainty.replicates_successful == result.bootstrap_successful
    assert (
        uncertainty.selected_mae.confidence_level
        == uncertainty.selected_r2.confidence_level
        == 0.90
    )
    assert uncertainty.selected_mae.lower < uncertainty.selected_mae.upper
    assert (
        tuple(interval.candidate for interval in uncertainty.paired_deltas)
        == nested.CANDIDATE_ORDER
    )
    assert all(
        interval.mae_difference.replicates == result.bootstrap_successful
        for interval in uncertainty.paired_deltas
    )
    assert (
        sum(count.fold_decisions for count in uncertainty.selection_counts)
        == uncertainty.selection_decision_denominator
    )
    assert (
        sum(count.comparison_observations for count in uncertainty.selection_counts)
        == uncertainty.comparison_observation_denominator
    )
    assert (
        4 * result.bootstrap_successful
        <= uncertainty.selection_decision_denominator
        <= 5 * result.bootstrap_successful
    )
    assert (
        60 * result.bootstrap_successful
        <= uncertainty.comparison_observation_denominator
        <= 96 * result.bootstrap_successful
    )


def test_joint_row_permutation_replays_full_selection_and_bootstrap_without_legacy_changes(
    arrays, result
):
    before = algorithm_profile().model_dump(mode="json")
    snapshots = tuple(value.tobytes() for value in arrays)
    order = np.random.default_rng(33).permutation(96)
    replay = nested.fit_nested_selection_gene(
        *(values[order] for values in arrays), request_digest=DIGEST
    )
    assert asdict(replay) == asdict(result)
    assert snapshots == tuple(value.tobytes() for value in arrays)
    assert algorithm_profile().model_dump(mode="json") == before
    assert legacy.DiscordanceFitConfiguration().minimum_train_complete == 48
    assert legacy.DiscordanceFitConfiguration().minimum_oof == 60
    assert legacy.DiscordanceFitConfiguration().bootstrap_replicates == 128


def test_low_complete_case_genes_remain_abstained_before_any_bootstrap(arrays):
    cnv, rna, protein, folds = (values.copy() for values in arrays)
    protein[40:] = np.nan
    result = nested.fit_nested_selection_gene(cnv, rna, protein, folds, request_digest=DIGEST)
    assert not result.accepted
    assert result.complete_count == 40
    assert result.bootstrap_attempted == result.bootstrap_successful == 0
    assert result.uncertainty is None
    assert result.common_oof_count == 0
    assert result.point_summary is None
    assert all(trace.selection_basis == "outer_support_abstention" for trace in result.point_folds)


@pytest.mark.parametrize("successful", [102, 103])
def test_exact_bootstrap_gate_counts_failures_without_replacement(
    arrays, point, monkeypatch, successful
):
    canonical_order = legacy._canonical_row_order(*arrays)
    canonical = tuple(value[canonical_order] for value in arrays)
    random = np.random.default_rng(legacy._bootstrap_seed(DIGEST))
    expected_draws = [
        legacy._stratified_patient_bootstrap_indices(canonical[3], random) for _ in range(128)
    ]
    calls = 0

    def controlled_point(*values):
        nonlocal calls
        expected = (
            canonical
            if calls == 0
            else tuple(value[expected_draws[calls - 1]] for value in canonical)
        )
        assert all(
            np.array_equal(actual, expected_value)
            for actual, expected_value in zip(values, expected, strict=True)
        )
        calls += 1
        return point if calls == 1 or calls - 1 <= successful else replace(point, accepted=False)

    monkeypatch.setattr(nested, "nested_point_fit", controlled_point)
    result = nested.fit_nested_selection_gene(*arrays, request_digest=DIGEST)
    assert calls == 129
    assert result.bootstrap_successful == successful
    assert result.bootstrap_attempted == 128
    assert result.accepted is (successful >= 103)
    assert (result.uncertainty is not None) is (successful >= 103)
    if successful < 103:
        assert "103" in result.failure_reason


def test_aggregate_receipts_are_json_safe_without_patient_vectors_or_biological_labels(result):
    document = asdict(result)
    encoded = json.dumps(document, allow_nan=False)
    assert "observed_protein" not in encoded
    assert "selected_predictions" not in encoded
    assert "fixed_predictions" not in encoded
    assert "conditional_rna_slope" not in encoded
    assert "pattern" not in document
    with pytest.raises(FrozenInstanceError):
        result.accepted = False


def test_transient_point_arrays_are_immutable_repr_hidden_and_nonpickleable(point):
    assert "array(" not in repr(point)
    for values in (
        point.observed,
        point.selected_predictions,
        *point.fixed_predictions,
        point.comparison_mask,
    ):
        assert not values.flags.writeable
        with pytest.raises(ValueError):
            values.setflags(write=True)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(point)
    with pytest.raises(TypeError, match="cannot be serialized"):
        point.__getstate__()


def test_candidate_fit_does_not_predict_when_failed_and_rejects_unknown_family(arrays):
    cnv, rna, protein, _folds = arrays
    failed = nested.CandidateFit("full", None, None, "known numerical failure")
    with pytest.raises(ValueError, match="unavailable"):
        failed.predict(cnv, rna)
    with pytest.raises(ValueError, match="unknown"):
        nested._fit_candidate("arbitrary", cnv, rna, protein, outer_fold=0, inner_fold=1)


@pytest.mark.parametrize(
    ("index", "replacement", "error"),
    [
        (0, [1.0] * 96, TypeError),
        (0, np.ones(96, dtype=int), TypeError),
        (0, np.ones((96, 1)), ValueError),
        (0, np.full(96, np.inf), ValueError),
        (0, np.full(96, nested.MAX_ABSOLUTE_INPUT + 1.0), ValueError),
        (0, np.ones(95), ValueError),
        (3, np.zeros(96, dtype=np.int8), ValueError),
    ],
)
def test_malformed_arrays_fail_closed(arrays, index, replacement, error):
    inputs = list(arrays)
    inputs[index] = replacement
    with pytest.raises(error):
        nested.fit_nested_selection_gene(*inputs, request_digest=DIGEST)


@pytest.mark.parametrize("digest", ["", "not-a-digest", "sha256:" + "g" * 64])
def test_invalid_seed_binding_is_rejected_before_fitting(arrays, digest):
    with pytest.raises(ValueError):
        nested.fit_nested_selection_gene(*arrays, request_digest=digest)

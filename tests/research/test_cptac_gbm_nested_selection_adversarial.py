"""Adversarial training-boundary and matched-support tests for nested selection."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    model as legacy,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    nested_selection as nested,
)
from tools import evaluate_cptac_gbm_nested_selection as runner

if TYPE_CHECKING:
    from pathlib import Path

DIGEST = "sha256:" + "b" * 64


def _gene(count: int = 100) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    random = np.random.default_rng(1_901)
    cnv = random.normal(size=count)
    rna = 0.15 * cnv + random.normal(size=count)
    protein = 1.3 * rna + 0.9 * cnv + random.normal(scale=0.12, size=count)
    return cnv, rna, protein, (np.arange(count) % 5).astype(np.int8)


def _trace(point: nested.NestedPointFit, fold: int) -> nested.OuterSelectionTrace:
    return next(trace for trace in point.fold_trace if trace.fold == fold)


def _candidate(
    evidence: tuple[nested.CandidateSelectionEvidence, ...],
    candidate: str,
) -> nested.CandidateSelectionEvidence:
    return next(item for item in evidence if item.candidate == candidate)


def test_outer_test_outcome_poison_cannot_change_its_selection_or_refit_predictions() -> None:
    cnv, rna, protein, folds = _gene()
    reference = nested.nested_point_fit(cnv, rna, protein, folds)
    poisoned = protein.copy()
    poisoned[folds == 0] = 1_000_000.0 - 3_000.0 * poisoned[folds == 0]
    current = nested.nested_point_fit(cnv, rna, poisoned, folds)
    before, after = _trace(reference, 0), _trace(current, 0)
    assert before.selection_basis == after.selection_basis
    assert before.selected_candidate == after.selected_candidate
    assert before.candidates == after.candidates
    assert before.outer_fits == after.outer_fits
    assert np.array_equal(
        reference.selected_predictions[folds == 0],
        current.selected_predictions[folds == 0],
        equal_nan=True,
    )
    for first, second in zip(reference.fixed_predictions, current.fixed_predictions, strict=True):
        assert np.array_equal(first[folds == 0], second[folds == 0], equal_nan=True)
    # Final test errors are expected to change; they are not selection inputs.
    assert reference.summary is not None and current.summary is not None
    assert reference.summary.selected.mae != current.summary.selected.mae


def test_every_inner_and_outer_transform_is_fitted_on_its_exact_training_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cnv, rna, protein, folds = _gene()
    protein[7] = np.nan
    rna[19] = np.nan
    original = nested._fit_candidate
    contexts: set[tuple[int, int | None, str]] = set()

    def audited_fit(
        candidate: str,
        *training: np.ndarray,
        outer_fold: int,
        inner_fold: int | None,
    ) -> nested.CandidateFit:
        training_cnv, training_rna, training_protein = training
        mask = (folds != outer_fold) & np.isfinite(cnv) & np.isfinite(rna) & np.isfinite(protein)
        if inner_fold is not None:
            mask &= folds != inner_fold
        expected = set(zip(cnv[mask], rna[mask], protein[mask], strict=True))
        supplied = set(zip(training_cnv, training_rna, training_protein, strict=True))
        assert supplied == expected
        assert len(training_protein) == int(mask.sum())
        contexts.add((outer_fold, inner_fold, candidate))
        attempt = original(
            candidate,
            training_cnv,
            training_rna,
            training_protein,
            outer_fold=outer_fold,
            inner_fold=inner_fold,
        )
        if attempt.model is not None:
            features = {
                "full": np.column_stack((training_rna, training_cnv)),
                "rna_only": training_rna[:, None],
                "cnv_only": training_cnv[:, None],
            }[candidate]
            assert np.array_equal(attempt.model.x_center, np.median(features, axis=0))
            expected_scale = (
                np.median(np.abs(features - np.median(features, axis=0)), axis=0) * 1.4826
            )
            assert np.array_equal(attempt.model.x_scale, expected_scale)
            assert attempt.model.y_center == float(np.median(training_protein))
        if candidate == "training_median":
            assert attempt.median == float(np.median(training_protein))
        return attempt

    monkeypatch.setattr(nested, "_fit_candidate", audited_fit)
    point = nested.nested_point_fit(cnv, rna, protein, folds)
    assert point.accepted
    assert contexts == {
        (outer, inner, candidate)
        for outer in range(5)
        for inner in (*[fold for fold in range(5) if fold != outer], None)
        for candidate in nested.CANDIDATE_ORDER
    }


def test_outer_test_covariate_shift_cannot_change_training_transforms_or_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _gene()
    cnv, rna, protein, folds = values
    original = nested._fit_candidate
    recorded: list[tuple[str, int | None, bytes, bytes, bytes, float, float]] = []

    def record(
        candidate: str,
        *training: np.ndarray,
        outer_fold: int,
        inner_fold: int | None,
    ) -> nested.CandidateFit:
        first, second, third = training
        attempt = original(
            candidate, first, second, third, outer_fold=outer_fold, inner_fold=inner_fold
        )
        if outer_fold == 0 and attempt.model is not None:
            model = attempt.model
            recorded.append(
                (
                    candidate,
                    inner_fold,
                    model.x_center.tobytes(),
                    model.x_scale.tobytes(),
                    model.beta.tobytes(),
                    model.y_center,
                    model.y_scale,
                )
            )
        return attempt

    monkeypatch.setattr(nested, "_fit_candidate", record)
    reference = nested.nested_point_fit(*values)
    expected = list(recorded)
    recorded.clear()
    shifted_cnv, shifted_rna = cnv.copy(), rna.copy()
    shifted_cnv[folds == 0] += 1_000_000.0
    shifted_rna[folds == 0] -= 2_000_000.0
    current = nested.nested_point_fit(shifted_cnv, shifted_rna, protein, folds)
    assert recorded == expected
    assert _trace(current, 0).candidates == _trace(reference, 0).candidates
    assert _trace(current, 0).selected_candidate == _trace(reference, 0).selected_candidate


def test_failure_in_one_inner_block_disqualifies_candidate_instead_of_scoring_remaining_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cnv, rna, protein, folds = _gene()
    training = folds != 0
    original = nested._fit_candidate

    def one_block_failure(
        candidate: str,
        *arrays: np.ndarray,
        outer_fold: int,
        inner_fold: int | None,
    ) -> nested.CandidateFit:
        attempt = original(candidate, *arrays, outer_fold=outer_fold, inner_fold=inner_fold)
        if candidate == "full" and inner_fold == 2:
            return replace(attempt, median=None, model=None, failure_reason="forced inner failure")
        return attempt

    monkeypatch.setattr(nested, "_fit_candidate", one_block_failure)
    selection = nested._inner_select(
        cnv[training], rna[training], protein[training], folds[training], outer_fold=0
    )
    full = _candidate(selection.candidates, "full")
    assert full.eligible is False
    assert full.inner_oof_count == 60
    assert full.inner_mae is None
    assert any("forced inner failure" in reason for reason in full.failure_reasons)
    assert selection.selected_candidate != "full"
    for name in nested.CANDIDATE_ORDER[:-1]:
        evidence = _candidate(selection.candidates, name)
        assert evidence.eligible and evidence.inner_oof_count == 80


@pytest.mark.parametrize(
    ("counts", "basis"),
    [([10, 10, 11, 11], "fallback_inner_support"), ([10, 11, 11, 11], "inner_mae")],
)
def test_new_inner_training_boundary_is_31_vs_32_not_a_silent_outer_gate_change(
    counts: list[int],
    basis: str,
) -> None:
    random = np.random.default_rng(771)
    folds = np.concatenate(
        [np.full(count, index + 1, dtype=np.int8) for index, count in enumerate(counts)]
    )
    cnv = random.normal(size=len(folds))
    rna = random.normal(size=len(folds))
    protein = rna + 0.8 * cnv + random.normal(scale=0.1, size=len(folds))
    selection = nested._inner_select(cnv, rna, protein, folds, outer_fold=0)
    assert selection.selection_basis == basis
    if basis == "fallback_inner_support":
        assert selection.selected_candidate == "training_median"
        assert all(item.inner_mae is None for item in selection.candidates)
        assert selection.fallback_reason is not None
    else:
        assert all(
            item.inner_oof_count == len(folds) for item in selection.candidates if item.eligible
        )


def test_subquantization_mae_improvement_is_not_rounded_into_a_simplicity_tie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cnv, rna, _protein, folds = _gene()
    training = folds != 0
    errors = {"training_median": 3e-10, "rna_only": 2e-10, "cnv_only": 1e-10, "full": 0.5e-10}

    def known_predictions(
        candidate: str, *_arrays: np.ndarray, **_context: int
    ) -> nested.CandidateFit:
        return nested.CandidateFit(candidate, errors[candidate], None, None)

    monkeypatch.setattr(nested, "_fit_candidate", known_predictions)
    selection = nested._inner_select(
        cnv[training], rna[training], np.zeros(int(training.sum())), folds[training], outer_fold=0
    )
    assert selection.selected_candidate == "full"
    assert all(
        round(item.inner_mae, 8) == 0 for item in selection.candidates if item.inner_mae is not None
    )


@pytest.mark.parametrize(
    ("errors", "unavailable", "expected"),
    [
        ((1.0, 1.0, 1.0, 1.0), None, "training_median"),
        ((2.0, 1.0, 1.0, 1.0), None, "rna_only"),
        ((2.0, 1.0, 1.0, 1.0), "rna_only", "cnv_only"),
    ],
)
def test_exact_mae_ties_use_the_frozen_simplicity_order_and_skip_failed_candidates(
    monkeypatch: pytest.MonkeyPatch,
    errors: tuple[float, ...],
    unavailable: str | None,
    expected: str,
) -> None:
    cnv, rna, _protein, folds = _gene()
    training = folds != 0
    assert nested.CANDIDATE_ORDER == ("training_median", "rna_only", "cnv_only", "full")
    prediction = dict(zip(nested.CANDIDATE_ORDER, errors, strict=True))

    def equal_errors(candidate: str, *_arrays: np.ndarray, **_context: int) -> nested.CandidateFit:
        if candidate == unavailable:
            return nested.CandidateFit(candidate, None, None, "candidate unavailable in tie oracle")
        return nested.CandidateFit(candidate, prediction[candidate], None, None)

    monkeypatch.setattr(nested, "_fit_candidate", equal_errors)
    selected = nested._inner_select(
        cnv[training],
        rna[training],
        np.zeros(int(training.sum())),
        folds[training],
        outer_fold=0,
    )
    assert selected.selection_basis == "inner_mae"
    assert selected.selected_candidate == expected
    if unavailable is not None:
        failed = _candidate(selected.candidates, unavailable)
        assert failed.eligible is False and failed.inner_mae is None


def test_selected_outer_refit_failure_is_explicit_and_fixed_comparisons_use_one_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _gene()
    folds = values[3]
    reference = nested.nested_point_fit(*values)
    assert _trace(reference, 0).selected_candidate == "full"
    original = nested._fit_candidate

    def failed_outer(
        candidate: str,
        *arrays: np.ndarray,
        outer_fold: int,
        inner_fold: int | None,
    ) -> nested.CandidateFit:
        attempt = original(candidate, *arrays, outer_fold=outer_fold, inner_fold=inner_fold)
        if candidate == "full" and outer_fold == 0 and inner_fold is None:
            return replace(
                attempt, model=None, median=None, failure_reason="forced outer refit failure"
            )
        return attempt

    monkeypatch.setattr(nested, "_fit_candidate", failed_outer)
    point = nested.nested_point_fit(*values)
    trace = _trace(point, 0)
    assert trace.selection_basis == "fallback_selected_refit"
    assert trace.selected_candidate == "training_median"
    assert point.selected_oof_count == 100
    assert point.common_oof_count == 80
    assert not bool(np.any(point.comparison_mask[folds == 0]))
    assert bool(np.all(point.comparison_mask[folds != 0]))
    assert bool(np.all(np.isnan(point.fixed_predictions[-1][folds == 0])))
    assert bool(np.all(np.isfinite(point.fixed_predictions[0][folds == 0])))
    assert point.summary is not None
    assert point.summary.selected.observed_count == 80
    assert all(metric.observed_count == 80 for metric in point.summary.fixed)
    assert point.summary.selection_decision_denominator == 4


def test_full_prediction_fault_in_all_inner_blocks_and_outer_refit_keeps_honest_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cnv, rna, protein, folds = _gene()
    original_fit, original_predict = nested._fit_candidate, nested.CandidateFit.predict
    retained: list[nested.CandidateFit] = []
    fault_context: dict[int, int | None] = {}
    faulted: set[int | None] = set()

    def tagged_fit(
        candidate: str,
        *arrays: np.ndarray,
        outer_fold: int,
        inner_fold: int | None,
    ) -> nested.CandidateFit:
        attempt = original_fit(candidate, *arrays, outer_fold=outer_fold, inner_fold=inner_fold)
        if candidate == "full" and outer_fold == 0:
            retained.append(attempt)  # Keep identities live for the injected prediction fault.
            fault_context[id(attempt)] = inner_fold
        return attempt

    def failed_prediction(
        attempt: nested.CandidateFit,
        held_cnv: np.ndarray,
        held_rna: np.ndarray,
    ) -> np.ndarray:
        if id(attempt) in fault_context:
            faulted.add(fault_context[id(attempt)])
            return np.full(len(held_cnv), np.nan, dtype=np.float64)
        return original_predict(attempt, held_cnv, held_rna)

    monkeypatch.setattr(nested, "_fit_candidate", tagged_fit)
    monkeypatch.setattr(nested.CandidateFit, "predict", failed_prediction)
    point = nested.nested_point_fit(cnv, rna, protein, folds)
    trace = _trace(point, 0)
    full = _candidate(trace.candidates, "full")
    assert faulted == {1, 2, 3, 4, None}
    assert full.eligible is False and full.inner_oof_count == 0 and full.inner_mae is None
    assert len(full.failure_reasons) == 4
    assert all("non-finite prediction" in reason for reason in full.failure_reasons)
    assert trace.selected_candidate != "full" and trace.selected_prediction_available
    outer_full = next(item for item in trace.outer_fits if item.candidate == "full")
    assert outer_full.available is False
    assert outer_full.failure_reason == "non-finite outer prediction"
    assert point.selected_oof_count == 100 and point.common_oof_count == 80
    assert bool(np.all(np.isfinite(point.selected_predictions[folds == 0])))
    assert bool(np.all(np.isnan(point.fixed_predictions[-1][folds == 0])))
    assert not bool(np.any(point.comparison_mask[folds == 0]))
    assert bool(np.all(point.comparison_mask[folds != 0]))
    assert point.accepted and point.summary is not None
    assert point.summary.selected.observed_count == 80
    full_metric = next(metric for metric in point.summary.fixed if metric.candidate == "full")
    mask = point.comparison_mask
    expected_full_mae = float(np.mean(np.abs(protein[mask] - point.fixed_predictions[-1][mask])))
    assert full_metric.observed_count == 80
    assert full_metric.mae == expected_full_mae and full_metric.mae > 0
    assert point.summary.selected.mae == float(
        np.mean(np.abs(protein[mask] - point.selected_predictions[mask]))
    )


def test_nonfinite_predictions_from_every_family_cannot_fabricate_a_null_or_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cnv, rna, protein, folds = _gene()

    def nonfinite(
        _attempt: nested.CandidateFit,
        held_cnv: np.ndarray,
        _held_rna: np.ndarray,
    ) -> np.ndarray:
        return np.full(len(held_cnv), np.nan, dtype=np.float64)

    monkeypatch.setattr(nested.CandidateFit, "predict", nonfinite)
    training = folds != 0
    selection = nested._inner_select(
        cnv[training],
        rna[training],
        protein[training],
        folds[training],
        outer_fold=0,
    )
    assert selection.selection_basis == "fallback_inner_support"
    assert selection.selected_candidate == "training_median"
    assert selection.fallback_reason == "no candidate had complete finite inner OOF support"
    assert all(
        not candidate.eligible and candidate.inner_mae is None for candidate in selection.candidates
    )
    assert all(candidate.inner_oof_count == 0 for candidate in selection.candidates)
    point = nested.nested_point_fit(cnv, rna, protein, folds)
    assert not point.accepted and point.summary is None
    assert point.selected_oof_count == point.common_oof_count == 0
    assert bool(np.all(np.isnan(point.selected_predictions)))
    assert bool(np.all(np.isnan(point.observed)))
    assert all(bool(np.all(np.isnan(values))) for values in point.fixed_predictions)
    assert not bool(np.any(point.comparison_mask))
    assert all(
        not trace.selected_prediction_available and not trace.comparison_accepted
        for trace in point.fold_trace
    )
    assert all(trace.selection_basis == "fallback_selected_refit" for trace in point.fold_trace)
    assert all(
        item.failure_reason == "non-finite outer prediction"
        for trace in point.fold_trace
        for item in trace.outer_fits
    )
    result = nested.fit_nested_selection_gene(cnv, rna, protein, folds, request_digest=DIGEST)
    assert not result.accepted and result.point_summary is None and result.uncertainty is None
    assert result.bootstrap_requested == 128
    assert result.bootstrap_attempted == result.bootstrap_successful == 0
    assert result.failure_reason is not None


def _aggregate_only(value: object) -> None:
    assert not isinstance(value, np.ndarray)
    if isinstance(value, dict):
        assert not {
            "observed",
            "selected_predictions",
            "fixed_predictions",
            "comparison_mask",
            "patient_ids",
        }.intersection(value)
        for child in value.values():
            _aggregate_only(child)
    elif isinstance(value, (list, tuple)):
        assert len(value) not in (96, 100)
        for child in value:
            _aggregate_only(child)


def test_every_bootstrap_draw_reruns_inner_selection_and_real_runner_persists_only_aggregates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    values = _gene()
    order = legacy._canonical_row_order(*values)
    canonical = tuple(value[order] for value in values)
    random = np.random.default_rng(legacy._bootstrap_seed(DIGEST))
    expected = [
        legacy._stratified_patient_bootstrap_indices(canonical[3], random) for _ in range(128)
    ]
    original_point, original_inner = nested.nested_point_fit, nested._inner_select
    point_calls = inner_calls = 0

    def refit(*arrays: np.ndarray) -> nested.NestedPointFit:
        nonlocal point_calls
        frame = (
            canonical
            if point_calls == 0
            else tuple(value[expected[point_calls - 1]] for value in canonical)
        )
        assert all(np.array_equal(left, right) for left, right in zip(arrays, frame, strict=True))
        point_calls += 1
        return original_point(*arrays)

    def select(*arrays: np.ndarray, outer_fold: int) -> nested.InnerSelection:
        nonlocal inner_calls
        inner_calls += 1
        assert outer_fold not in np.unique(arrays[3])
        return original_inner(*arrays, outer_fold=outer_fold)

    monkeypatch.setattr(nested, "nested_point_fit", refit)
    monkeypatch.setattr(nested, "_inner_select", select)
    result = nested.fit_nested_selection_gene(*values, request_digest=DIGEST)
    assert result.accepted
    assert result.bootstrap_requested == result.bootstrap_attempted == 128
    assert point_calls == 129
    assert inner_calls == 5 * point_calls
    assert result.uncertainty is not None
    assert result.uncertainty.selection_decision_denominator == 5 * result.bootstrap_successful
    document = asdict(result)
    _aggregate_only(document)
    path = tmp_path / "nested-aggregate.json"
    runner._write_json(path, document)
    saved = json.loads(path.read_text(encoding="utf-8"))
    _aggregate_only(saved)
    assert saved["accepted"] is True

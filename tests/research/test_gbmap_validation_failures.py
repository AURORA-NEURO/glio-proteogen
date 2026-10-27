"""Whole-family conservation and fail-closed final-training regressions."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from types import SimpleNamespace

import pytest

from glio_proteogen.research.gbmap_deconvolution import training
from glio_proteogen.research.gbmap_deconvolution.errors import GbmapInputError, GbmapNumericalError
from glio_proteogen.research.gbmap_deconvolution.splits import (
    build_validation_split_plan,
    within_study_holdout_coverage,
)
from tests.research.test_gbmap_development_diagnostics import _marker_reference


def _reference():
    return _marker_reference(studies=4, donors=6)


def _with_folds(plan, folds):
    canonical = tuple(sorted(folds, key=lambda fold: fold.fold_id))
    return replace(
        plan,
        folds=canonical,
        receipt=replace(
            plan.receipt, folds=tuple(fold.deidentified_receipt() for fold in canonical)
        ),
    )


def _require_structural_support(reference):
    plan = build_validation_split_plan(reference)
    whole = tuple(fold for fold in plan.folds if fold.kind == "whole_study")
    within = tuple(fold for fold in plan.folds if fold.kind == "within_study_donor")
    assert len(whole) == 4
    assert len(within) == 5
    assert all(fold.evaluable for fold in plan.folds)
    assert all(sum(label.evaluable for label in fold.label_support) == 2 for fold in plan.folds)
    return plan, whole, within


def _fold_evaluation(prepared, shrinkage, *, failed=False):
    assert type(prepared) is training._PreparedFold
    return training.CandidateFoldEvaluation(
        fold_id=prepared.fold.fold_id,
        kind=prepared.fold.kind,
        shrinkage=shrinkage,
        state="abstained" if failed else "evaluated",
        abstention_reason="hierarchy_did_not_converge" if failed else None,
        eligible_lineage_count=len(prepared.labels),
        selected_feature_count=len(prepared.feature_indices),
        evaluated_held_record_count=0 if failed else len(prepared.held_records),
        mean_per_count_nll=None if failed else 0.2,
    )


def test_duplicate_whole_study_donor_evidence_is_rejected_despite_unique_fold_identifiers():
    plan, whole, _within = _require_structural_support(_reference())
    duplicate = replace(whole[0], fold_id="whole-study-9000")
    malformed = _with_folds(plan, (*plan.folds, duplicate))
    assert len({fold.fold_id for fold in malformed.folds}) == len(malformed.folds)
    with pytest.raises(GbmapInputError, match="whole-study coverage repeats a grouped donor"):
        within_study_holdout_coverage(malformed)


@pytest.mark.parametrize("missing", ["one_fold", "entire_family"])
def test_missing_whole_study_evidence_cannot_be_inferred_from_retained_within_folds(missing):
    plan, whole, within = _require_structural_support(_reference())
    retained = (
        tuple(fold for fold in plan.folds if fold is not whole[0])
        if missing == "one_fold"
        else within
    )
    malformed = _with_folds(plan, retained)
    assert tuple(fold for fold in malformed.folds if fold.kind == "within_study_donor") == within
    with pytest.raises(
        GbmapInputError, match=r"grouped-donor axis|whole-study coverage is missing"
    ):
        within_study_holdout_coverage(malformed)


@pytest.mark.parametrize("failed_family", ["whole_study", "within_study_donor"])
def test_public_training_rejects_every_candidate_missing_numerical_family_support(
    monkeypatch, failed_family
):
    reference = _reference()
    plan, whole, within = _require_structural_support(reference)
    failures = {
        fold.fold_id for fold in (whole[:2] if failed_family == "whole_study" else within[:1])
    }
    observed = defaultdict(list)

    def evaluate(prepared, shrinkage, _configuration, _cancellation):
        result = _fold_evaluation(prepared, shrinkage, failed=prepared.fold.fold_id in failures)
        observed[shrinkage].append(result)
        return result

    def forbidden(*_args, **_kwargs):
        pytest.fail("insufficient numerical validation must stop before final fitting or a model")

    monkeypatch.setattr(training, "_evaluate_prepared_fold", evaluate)
    monkeypatch.setattr(training, "_final_fit", forbidden)
    monkeypatch.setattr(training, "_fit_label", forbidden)
    monkeypatch.setattr(training, "DevelopmentCandidateModel", forbidden)
    monkeypatch.setattr(training, "DevelopmentTrainingResult", forbidden)
    with pytest.raises(GbmapInputError, match="no shrinkage candidate satisfies both"):
        training.train_development_candidate(reference)

    assert tuple(observed) == training.DEFAULT_SHRINKAGE_GRID
    assert all(len(rows) == len(plan.folds) for rows in observed.values())
    expected = (2, 5) if failed_family == "whole_study" else (4, 4)
    for rows in observed.values():
        assert (
            sum(row.kind == "whole_study" and row.state == "evaluated" for row in rows),
            sum(row.kind == "within_study_donor" and row.state == "evaluated" for row in rows),
        ) == expected


def test_final_nonconvergence_after_selected_coverage_never_returns_a_partial_model(monkeypatch):
    reference = _reference()
    plan, _whole, _within = _require_structural_support(reference)
    evaluated = defaultdict(list)
    final_calls = []
    selected_coverage = []
    actual_validation = training._validated_final_labels

    def evaluate(prepared, shrinkage, _configuration, _cancellation):
        result = _fold_evaluation(prepared, shrinkage)
        evaluated[shrinkage].append(result)
        return result

    def covered(*args):
        labels = actual_validation(*args)
        selected_coverage.append(labels)
        return labels

    def final_fit(records, *, reference: object, label, shrinkage, **_kwargs):
        assert reference is fixture
        assert len(records) == len(fixture.records)
        assert shrinkage == training.DEFAULT_SHRINKAGE_GRID[0]
        final_calls.append(label)
        # The first admitted lineage succeeds, so failure of the second must
        # discard an already accumulated fit rather than return a partial model.
        return SimpleNamespace(converged=len(final_calls) == 1)

    def forbidden(*_args, **_kwargs):
        pytest.fail("a failed final lineage cannot emit any model or training result")

    fixture = reference
    monkeypatch.setattr(training, "_evaluate_prepared_fold", evaluate)
    monkeypatch.setattr(training, "_validated_final_labels", covered)
    monkeypatch.setattr(training, "_fit_label", final_fit)
    monkeypatch.setattr(training, "verify_hierarchy_trace", lambda _fit: True)
    monkeypatch.setattr(training, "DevelopmentCandidateModel", forbidden)
    monkeypatch.setattr(training, "DevelopmentTrainingResult", forbidden)
    with pytest.raises(GbmapNumericalError, match="final lineage hierarchy did not converge"):
        training.train_development_candidate(reference)

    assert tuple(evaluated) == training.DEFAULT_SHRINKAGE_GRID
    assert all(len(rows) == len(plan.folds) for rows in evaluated.values())
    assert all(row.state == "evaluated" for rows in evaluated.values() for row in rows)
    assert selected_coverage == [reference.modeled_labels]
    assert tuple(final_calls) == reference.modeled_labels

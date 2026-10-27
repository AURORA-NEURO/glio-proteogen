"""Selected-lineage support oracles using invented counts and programmed fits."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution import splits, training
from glio_proteogen.research.gbmap_deconvolution.aggregate import (
    AggregateReference,
    DonorLabelAggregate,
)
from glio_proteogen.research.gbmap_deconvolution.errors import GbmapInputError
from glio_proteogen.research.gbmap_deconvolution.feature_identity import GBMAP_SOURCE_SHA256
from glio_proteogen.research.gbmap_development_reduction import LINEAGE_POLICY_ID

LABELS = ("lineage-a", "lineage-b", "lineage-c")


def _reference() -> AggregateReference:
    records = []
    for study in range(5):
        for donor in range(3):
            for index, label in enumerate(LABELS):
                counts = np.full(36, 83, dtype=np.int64)
                counts[index * 12 : (index + 1) * 12] = 1500
                counts[(index * 12 + 12) % 36] += 8
                records.append(
                    DonorLabelAggregate(
                        donor_key=f"invented-{study}-{donor}",
                        study_key=f"study-{study}",
                        modeled_label=label,
                        source_labels=(label,),
                        cell_count=40,
                        gene_counts=counts,
                        detected_cell_counts=np.full(36, 30, dtype=np.int32),
                        total_umis=20000,
                    )
                )
    return AggregateReference(
        feature_ids=tuple(f"invented-feature-{x:03d}" for x in range(36)),
        gene_symbols=(None,) * 36,
        records=tuple(records),
        source_file_sha256="sha256:" + "1" * 64,
        source_bytes=99,
        taxonomy_digest="sha256:" + "2" * 64,
        extraction_recipe_digest="sha256:" + "3" * 64,
    )


def _prepared(
    reference: AggregateReference, *, whole: int = 3, within: int = 5, rare: bool = False
) -> tuple[Any, ...]:
    donor_study = {r.donor_key: r.study_key for r in reference.records}
    donors = tuple(sorted(donor_study))
    result = []
    for kind, count in (("whole_study", whole), ("within_study_donor", within)):
        for number in range(count):
            held = tuple(
                d
                for i, d in enumerate(donors)
                if (
                    donor_study[d] == f"study-{number}"
                    if kind == "whole_study"
                    else i % within == number
                )
            )
            prefix = "whole-study" if kind == "whole_study" else "within-study-donor"
            fold = splits._fold(
                fold_id=f"{prefix}-{number + 1:04d}",
                kind=kind,
                training_donors=tuple(d for d in donors if d not in held),
                held_donors=held,
                donor_study=donor_study,
                usable_records=reference.records,
                labels=LABELS,
            )
            labels = (
                LABELS if not rare or number < (3 if kind == "whole_study" else 5) else LABELS[:2]
            )
            features = tuple(range(len(labels) * 12))
            result.append(
                training._PreparedFold(
                    reference=reference,
                    fold=fold,
                    feature_indices=features,
                    labels=labels,
                    stable_gene_counts=tuple((label, 12) for label in labels),
                    training_records=tuple(r for r in reference.records if r.donor_key not in held),
                    held_records=tuple(r for r in reference.records if r.donor_key in held),
                    background=np.full(len(features), 1 / len(features)),
                )
            )
    return tuple(result)


def _candidate(
    prepared: tuple[Any, ...],
    configuration: training.TrainingConfiguration,
    *,
    failed: tuple[str, ...] = (),
    shrinkage: float = 1.0,
    score: float = 1.0,
) -> training.ShrinkageCandidateEvaluation:
    folds = tuple(
        training.CandidateFoldEvaluation(
            fold_id=p.fold.fold_id,
            kind=p.fold.kind,
            shrinkage=shrinkage,
            state="abstained" if p.fold.fold_id in failed else "evaluated",
            abstention_reason="hierarchy_fit_failed" if p.fold.fold_id in failed else None,
            eligible_lineage_count=len(p.labels),
            selected_feature_count=len(p.feature_indices),
            evaluated_held_record_count=0 if p.fold.fold_id in failed else len(p.labels),
            mean_per_count_nll=None if p.fold.fold_id in failed else score,
        )
        for p in prepared
    )
    whole = sum(f.state == "evaluated" and f.kind == "whole_study" for f in folds)
    within = sum(f.state == "evaluated" and f.kind == "within_study_donor" for f in folds)
    selectable = (
        whole >= configuration.minimum_whole_study_folds
        and within >= configuration.minimum_within_study_donor_folds
    )
    return training.ShrinkageCandidateEvaluation(
        shrinkage=shrinkage,
        folds=folds,
        whole_study_fold_count=whole,
        within_study_donor_fold_count=within,
        minimum_whole_study_folds=configuration.minimum_whole_study_folds,
        minimum_within_study_donor_folds=configuration.minimum_within_study_donor_folds,
        whole_study_mean_nll=score if whole else None,
        within_study_donor_mean_nll=score if within else None,
        selection_score=score if selectable else None,
        selectable=selectable,
    )


def test_policy_constants_match_new_pure_ledger_policy() -> None:
    assert training.FINAL_LINEAGE_VALIDATION_POLICY_ID == LINEAGE_POLICY_ID
    assert (training.MIN_FINAL_WHOLE_STUDY_FOLDS, training.MIN_FINAL_WITHIN_STUDY_DONOR_FOLDS) == (
        3,
        5,
    )


def test_overall_family_support_does_not_promote_missing_lineage_or_other_candidate() -> None:
    reference = _reference()
    config = training.DEFAULT_TRAINING_CONFIGURATION
    prepared = _prepared(reference, whole=4, within=6, rare=True)
    selected = _candidate(prepared, config, failed=("whole-study-0001", "within-study-donor-0001"))
    other = _candidate(prepared, config, shrinkage=10.0, score=2.0)
    assert selected.selectable and (
        selected.whole_study_fold_count,
        selected.within_study_donor_fold_count,
    ) == (3, 5)
    assert training._validated_final_labels(reference, selected, prepared, config) == LABELS[:2]
    assert training._validated_final_labels(reference, other, prepared, config) == LABELS


@pytest.mark.parametrize(("whole", "within"), [(2, 5), (3, 4), (1, 1)])
def test_exact_production_source_keeps_three_five_floors_under_lower_configuration(
    whole: int, within: int
) -> None:
    # Policy-routing seam only: no production extraction, feature admission or
    # hierarchy fitting is attempted on this invented reference.
    reference = replace(_reference(), source_file_sha256=GBMAP_SOURCE_SHA256)
    config = training.TrainingConfiguration(
        minimum_whole_study_folds=1, minimum_within_study_donor_folds=1
    )
    prepared = _prepared(reference, whole=whole, within=within)
    candidate = _candidate(prepared, config)
    assert candidate.selectable
    assert training._validated_final_labels(reference, candidate, prepared, config) == ()


def test_production_boundary_passes_three_five_and_higher_config_stays_stricter() -> None:
    reference = replace(_reference(), source_file_sha256=GBMAP_SOURCE_SHA256)
    low = training.TrainingConfiguration(
        minimum_whole_study_folds=1, minimum_within_study_donor_folds=1
    )
    prepared = _prepared(reference)
    assert (
        training._validated_final_labels(reference, _candidate(prepared, low), prepared, low)
        == LABELS
    )
    high = training.TrainingConfiguration(
        minimum_whole_study_folds=4, minimum_within_study_donor_folds=6
    )
    enough = _prepared(reference, whole=4, within=6)
    assert (
        training._validated_final_labels(reference, _candidate(enough, high), enough, high)
        == LABELS
    )


def test_generic_caller_owned_reference_can_use_its_explicit_configuration_minima() -> None:
    reference = _reference()
    config = training.TrainingConfiguration(
        minimum_whole_study_folds=1, minimum_within_study_donor_folds=1
    )
    prepared = _prepared(reference, whole=1, within=1)
    # With one within fold all donors would be held; this helper only checks the
    # selected prepared-label evidence. Split/fitting support remain independent.
    assert (
        training._validated_final_labels(reference, _candidate(prepared, config), prepared, config)
        == LABELS
    )


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_preparation",
        "duplicate_evidence",
        "missing_evidence",
        "family",
        "unprepared",
        "foreign_reference",
        "lineage_dimensions",
        "feature_dimensions",
        "label_axis",
    ],
)
def test_selected_evidence_must_match_exact_preparation_axis(change: str) -> None:
    reference = _reference()
    config = training.DEFAULT_TRAINING_CONFIGURATION
    prepared = _prepared(reference)
    selected = _candidate(prepared, config)
    if change == "duplicate_preparation":
        prepared = (*prepared[:-1], prepared[0])
    elif change == "duplicate_evidence":
        donor = next(x for x in selected.folds if x.kind == "within_study_donor")
        selected = replace(selected, folds=(*selected.folds[:-1], donor))
    elif change == "missing_evidence":
        prepared = prepared[:-1]
    elif change == "family":
        prepared = (
            replace(prepared[0], fold=replace(prepared[0].fold, kind="within_study_donor")),
            *prepared[1:],
        )
    elif change == "unprepared":
        prepared = (training._AbstainedFold(prepared[0].fold, "split_not_evaluable"), *prepared[1:])
    elif change == "foreign_reference":
        prepared = (replace(prepared[0], reference=_reference()), *prepared[1:])
    elif change == "lineage_dimensions":
        prepared = (replace(prepared[0], labels=LABELS[:2]), *prepared[1:])
    elif change == "feature_dimensions":
        prepared = (replace(prepared[0], feature_indices=(0, 1)), *prepared[1:])
    else:
        prepared = (replace(prepared[0], labels=tuple(reversed(LABELS))), *prepared[1:])
    with pytest.raises(GbmapInputError):
        training._validated_final_labels(reference, selected, prepared, config)


def test_unselectable_candidate_never_supplies_final_lineage_permission() -> None:
    reference = _reference()
    config = training.DEFAULT_TRAINING_CONFIGURATION
    prepared = _prepared(reference, whole=2, within=5)
    with pytest.raises(GbmapInputError, match="selectable"):
        training._validated_final_labels(reference, _candidate(prepared, config), prepared, config)


def _install_final_fit_spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[int, ...]]]:
    seen = []

    def fit(_records, *, reference, label, feature_indices, **_kwargs):
        assert reference is not None
        seen.append((label, feature_indices))
        return SimpleNamespace(
            converged=True, global_signature=np.full(len(feature_indices), 1 / len(feature_indices))
        )

    monkeypatch.setattr(training, "_fit_label", fit)
    monkeypatch.setattr(training, "verify_hierarchy_trace", lambda _fit: True)
    return seen


def test_final_fit_filters_before_feature_union_background_and_all_hierarchy_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference()
    seen = _install_final_fit_spy(monkeypatch)
    original = training._equal_label_study_background
    backgrounds = []

    def background(records, labels, features):
        backgrounds.append((labels, features))
        return original(records, labels, features)

    monkeypatch.setattr(training, "_equal_label_study_background", background)
    _selection, features, labels, fits = training._final_fit(
        reference, 1.0, training.DEFAULT_TRAINING_CONFIGURATION, None, validated_labels=LABELS[:2]
    )
    assert labels == LABELS[:2] and len(features) == 24 and all(index < 24 for index in features)
    assert tuple(label for label, _fit in fits) == LABELS[:2]
    assert tuple(label for label, _features in seen) == LABELS[:2]
    assert backgrounds == [(LABELS[:2], features)]


@pytest.mark.parametrize(
    "labels",
    [
        [],
        ["lineage-a", "lineage-b"],
        ("lineage-b", "lineage-a"),
        ("lineage-a", "lineage-a"),
        ("unknown", "lineage-a"),
        (True, "lineage-b"),
    ],
)
def test_final_fit_rejects_noncanonical_validation_labels(labels: Any) -> None:
    with pytest.raises(GbmapInputError, match="canonical"):
        training._final_fit(
            _reference(),
            1.0,
            training.DEFAULT_TRAINING_CONFIGURATION,
            None,
            validated_labels=labels,
        )


@pytest.mark.parametrize("labels", [(), ("lineage-a",)])
def test_fewer_than_two_validated_labels_stop_before_feature_union(
    monkeypatch: pytest.MonkeyPatch, labels: tuple[str, ...]
) -> None:
    def forbidden(*_args):
        pytest.fail("feature union must not run")

    monkeypatch.setattr(training, "_selected_features", forbidden)
    with pytest.raises(GbmapInputError, match="fewer than two"):
        training._final_fit(
            _reference(),
            1.0,
            training.DEFAULT_TRAINING_CONFIGURATION,
            None,
            validated_labels=labels,
        )


def test_private_generic_none_compatibility_does_not_change_original_source_support_floors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference()
    _install_final_fit_spy(monkeypatch)
    assert (
        training._final_fit(reference, 1.0, training.DEFAULT_TRAINING_CONFIGURATION, None)[2]
        == LABELS
    )
    reduced = replace(
        reference,
        records=tuple(
            r
            for r in reference.records
            if r.modeled_label != "lineage-c" or r.donor_key.endswith("-0")
        ),
    )
    with pytest.raises(GbmapInputError, match="fewer than two"):
        training._final_fit(
            reduced,
            1.0,
            training.DEFAULT_TRAINING_CONFIGURATION,
            None,
            validated_labels=("lineage-a", "lineage-c"),
        )


def test_public_training_passes_only_selected_candidates_covered_labels_to_final_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference()
    config = training.TrainingConfiguration(shrinkage_grid=(1.0, 10.0))
    prepared = _prepared(reference, whole=4, within=6, rare=True)
    by_id = {p.fold.fold_id: p for p in prepared}
    selected = _candidate(prepared, config, failed=("whole-study-0001", "within-study-donor-0001"))
    other = _candidate(prepared, config, shrinkage=10.0, score=2.0)
    monkeypatch.setattr(
        training,
        "build_validation_split_plan",
        lambda *_args, **_kwargs: SimpleNamespace(folds=tuple(p.fold for p in prepared)),
    )
    monkeypatch.setattr(
        training, "_prepare_fold", lambda _r, _plan, fold, *_args: by_id[fold.fold_id]
    )
    monkeypatch.setattr(
        training,
        "_candidate_evaluation",
        lambda _p, shrinkage, *_args: selected if shrinkage == 1.0 else other,
    )

    class FinalObservedError(Exception):
        pass

    def final(_r, shrinkage, *_args, validated_labels=None):
        assert _r is reference and shrinkage == 1.0 and validated_labels == LABELS[:2]
        raise FinalObservedError

    monkeypatch.setattr(training, "_final_fit", final)
    with pytest.raises(FinalObservedError):
        training.train_development_candidate(reference, configuration=config)


def test_public_training_abstains_when_only_one_lineage_passes_held_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference()
    config = training.DEFAULT_TRAINING_CONFIGURATION
    prepared = _prepared(reference)
    # Every fold still has two prepared labels; only lineage-a appears in all
    # 3/5 accepted folds. Overall-family success cannot promote b or c.
    prepared = tuple(
        replace(
            p,
            labels=("lineage-a", "lineage-b") if i % 2 else ("lineage-a", "lineage-c"),
            feature_indices=tuple(range(24)),
        )
        for i, p in enumerate(prepared)
    )
    by_id = {p.fold.fold_id: p for p in prepared}
    candidate = _candidate(prepared, config)
    monkeypatch.setattr(
        training,
        "build_validation_split_plan",
        lambda *_args, **_kwargs: SimpleNamespace(folds=tuple(p.fold for p in prepared)),
    )
    monkeypatch.setattr(
        training, "_prepare_fold", lambda _r, _plan, fold, *_args: by_id[fold.fold_id]
    )
    monkeypatch.setattr(training, "_candidate_evaluation", lambda *_args: candidate)

    def forbidden(*_args, **_kwargs):
        pytest.fail("no final hierarchy may run")

    monkeypatch.setattr(training, "_final_fit", forbidden)
    with pytest.raises(GbmapInputError, match="fewer than two lineages"):
        training.train_development_candidate(reference)

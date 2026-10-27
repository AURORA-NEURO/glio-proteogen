"""Metadata-only donor holdouts; singleton studies cannot poison a within fold."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, replace

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution.splits import (
    WITHIN_STUDY_SPLIT_POLICY_ID,
    build_validation_split_plan,
    within_study_holdout_coverage,
)
from glio_proteogen.research.gbmap_deconvolution.training import (
    MIN_EVALUABLE_WITHIN_STUDY_DONOR_FOLDS,
)
from tests.research.test_gbmap_splits import _reference


def _partitions(reference):
    plan = build_validation_split_plan(reference)
    within = tuple(fold for fold in plan.folds if fold.kind == "within_study_donor")
    whole = tuple(fold for fold in plan.folds if fold.kind == "whole_study")
    return plan, within, whole


def _study_donors(reference):
    groups = {}
    for record in reference.records:
        groups.setdefault(record.study_key, set()).add(record.donor_key)
    return groups


def _with_folds(plan, folds):
    return replace(
        plan,
        folds=tuple(folds),
        receipt=replace(plan.receipt, folds=tuple(fold.deidentified_receipt() for fold in folds)),
    )


def test_singleton_study_does_not_make_five_required_donor_folds_impossible():
    _, within, _ = _partitions(_reference((1, 12, 12, 12, 12)))
    assert MIN_EVALUABLE_WITHIN_STUDY_DONOR_FOLDS == 5
    assert len(within) == 5
    assert all(fold.evaluable for fold in within)
    assert all("no_same_study_training_donor" not in fold.abstention_reasons for fold in within)
    assert all(sum(item.evaluable for item in fold.label_support) == 2 for fold in within)


@pytest.mark.parametrize("sizes", [(1, 12, 12, 12, 12), (1, 1, 12, 12, 12, 12)])
def test_each_multidonor_is_held_once_and_singletons_stay_training_only_within(sizes):
    reference = _reference(sizes)
    _, within, whole = _partitions(reference)
    groups = _study_donors(reference)
    eligible = set().union(*(donors for donors in groups.values() if len(donors) >= 2))
    ineligible = set().union(*(donors for donors in groups.values() if len(donors) == 1))
    held_frequency = Counter(donor for fold in within for donor in fold.held_donor_keys)
    assert held_frequency == Counter(dict.fromkeys(eligible, 1))
    assert not ineligible.intersection(held_frequency)
    assert all(ineligible <= set(fold.training_donor_keys) for fold in within)
    whole_frequency = Counter(donor for fold in whole for donor in fold.held_donor_keys)
    assert whole_frequency == Counter(dict.fromkeys(eligible | ineligible, 1))


def test_every_within_held_study_has_a_different_training_donor():
    reference = _reference((1, 2, 3, 8, 12, 17))
    _, within, _ = _partitions(reference)
    groups = _study_donors(reference)
    all_donors = set().union(*groups.values())
    for fold in within:
        training, held = set(fold.training_donor_keys), set(fold.held_donor_keys)
        assert training.isdisjoint(held) and training | held == all_donors
        for study in fold.held_study_keys:
            assert groups[study] & held
            assert groups[study] & training
        assert set(fold.held_study_keys) <= set(fold.training_study_keys)


def test_singleton_studies_still_receive_separate_whole_study_holdouts():
    reference = _reference((1, 1, 12, 12, 12, 12))
    _, _, whole = _partitions(reference)
    groups = _study_donors(reference)
    for study, donors in groups.items():
        if len(donors) != 1:
            continue
        target = next(fold for fold in whole if fold.held_study_keys == (study,))
        assert set(target.held_donor_keys) == donors
        assert donors.isdisjoint(target.training_donor_keys)
        assert study not in target.training_study_keys


def test_all_singleton_source_has_no_fabricated_within_study_folds():
    _, within, whole = _partitions(_reference((1, 1, 1, 1)))
    assert within == ()
    assert len(whole) == 4
    assert all(fold.kind == "whole_study" for fold in whole)
    assert MIN_EVALUABLE_WITHIN_STUDY_DONOR_FOLDS == 5


def test_small_source_does_not_manufacture_five_evaluable_groups():
    _, within, _ = _partitions(_reference((1, 2, 2, 2, 2)))
    assert len(within) == 2
    assert sum(fold.evaluable for fold in within) < MIN_EVALUABLE_WITHIN_STUDY_DONOR_FOLDS
    assert all(set(fold.held_study_keys) <= set(fold.training_study_keys) for fold in within)


def test_permuting_records_does_not_change_donor_or_study_partitions():
    reference = _reference((1, 12, 12, 12, 12))
    reordered = replace(reference, records=tuple(reversed(reference.records)))
    assert build_validation_split_plan(reference) == build_validation_split_plan(reordered)


def test_gene_values_do_not_change_splits_when_metadata_eligibility_is_unchanged():
    reference = _reference((1, 12, 12, 12, 12))
    altered = replace(
        reference,
        records=tuple(
            replace(
                record,
                gene_counts=np.asarray((10_000, 30_000), dtype=np.int64),
                total_umis=40_000,
            )
            for record in reference.records
        ),
    )
    original_plan = build_validation_split_plan(reference)
    altered_plan = build_validation_split_plan(altered)
    assert original_plan.aggregate_content_digest != altered_plan.aggregate_content_digest
    assert original_plan.folds == altered_plan.folds
    assert asdict(original_plan.receipt) == asdict(altered_plan.receipt)


def test_all_lineage_records_for_a_donor_move_together_without_record_leakage():
    reference = _reference((1, 12, 12, 12, 12))
    plan = build_validation_split_plan(reference)
    records_by_donor = {}
    for record in reference.records:
        records_by_donor.setdefault(record.donor_key, set()).add(record.modeled_label)
    for fold in plan.folds:
        training, held = plan.partition_records(reference, fold.fold_id)
        assert {record.donor_key for record in training}.isdisjoint(
            record.donor_key for record in held
        )
        for subset in (training, held):
            observed = {}
            for record in subset:
                observed.setdefault(record.donor_key, set()).add(record.modeled_label)
            assert all(labels == records_by_donor[donor] for donor, labels in observed.items())


def test_one_grouped_donor_cannot_cross_study_boundaries():
    reference = _reference((1, 12, 12, 12, 12))
    first = reference.records[0]
    target = next(
        record
        for record in reference.records
        if record.study_key != first.study_key and record.modeled_label != first.modeled_label
    )
    records = tuple(
        replace(record, donor_key=first.donor_key) if record is target else record
        for record in reference.records
        if not (
            record.donor_key == first.donor_key and record.modeled_label == target.modeled_label
        )
    )
    with pytest.raises(ValueError, match="more than one study"):
        replace(reference, records=records)


def test_coverage_ledger_conserves_eligible_and_training_only_groups_without_identifiers():
    reference = _reference((1, 12, 12, 12, 12))
    plan = build_validation_split_plan(reference)
    ledger = asdict(within_study_holdout_coverage(plan))

    assert WITHIN_STUDY_SPLIT_POLICY_ID == "gbmap-within-study-eligible-donors/2.0.0"
    assert ledger == {
        "donor_groups_total": 49,
        "study_groups_total": 5,
        "within_eligible_donor_groups": 48,
        "within_ineligible_donor_groups": 1,
        "within_ineligible_study_groups": 1,
        "within_fold_count": 5,
        "held_once_eligible_donor_groups": 48,
        "unheld_eligible_donor_groups": 0,
        "repeated_within_donor_groups": 0,
        "held_ineligible_donor_groups": 0,
        "singleton_whole_study_covered_donor_groups": 1,
    }
    assert all(type(value) is int for value in ledger.values())
    document = json.dumps(ledger, sort_keys=True)
    assert all(record.donor_key not in document for record in reference.records)
    assert all(record.study_key not in document for record in reference.records)
    assert not any("keys" in key or "digest" in key for key in ledger)


def test_all_singleton_ledger_reports_training_only_coverage_without_claiming_within_support():
    plan = build_validation_split_plan(_reference((1, 1, 1, 1)))
    ledger = within_study_holdout_coverage(plan)
    assert ledger.donor_groups_total == ledger.study_groups_total == 4
    assert ledger.within_ineligible_donor_groups == ledger.within_ineligible_study_groups == 4
    assert ledger.singleton_whole_study_covered_donor_groups == 4
    assert ledger.within_eligible_donor_groups == ledger.within_fold_count == 0
    assert ledger.held_once_eligible_donor_groups == 0
    assert ledger.unheld_eligible_donor_groups == 0
    assert ledger.repeated_within_donor_groups == ledger.held_ineligible_donor_groups == 0


def test_study_eligibility_uses_eligible_grouped_donors_not_unusable_source_records():
    reference = _reference((2, 12, 12, 12))
    target = next(
        record.donor_key
        for record in reference.records
        if record.study_key == "study-0" and record.donor_key.endswith("01")
    )
    reference = replace(
        reference,
        records=tuple(
            replace(
                record,
                gene_counts=np.asarray((1_000, 1_000), dtype=np.int64),
                total_umis=2_000,
            )
            if record.donor_key == target
            else record
            for record in reference.records
        ),
    )
    plan, within, _ = _partitions(reference)
    ledger = within_study_holdout_coverage(plan)
    assert ledger.donor_groups_total == 37
    assert ledger.study_groups_total == 4
    assert ledger.within_eligible_donor_groups == ledger.held_once_eligible_donor_groups == 36
    assert ledger.within_ineligible_donor_groups == ledger.within_ineligible_study_groups == 1
    assert all("study-0" not in fold.held_study_keys for fold in within)
    assert all(target not in fold.training_donor_keys + fold.held_donor_keys for fold in within)


@pytest.mark.parametrize(
    "changes",
    [
        {"donor_groups_total": True},
        {"within_fold_count": 5.0},
        {"held_ineligible_donor_groups": -1},
    ],
)
def test_coverage_ledger_rejects_boolean_float_and_negative_counts(changes):
    plan = build_validation_split_plan(_reference((1, 12, 12, 12, 12)))
    with pytest.raises(ValueError):
        replace(within_study_holdout_coverage(plan), **changes)


def test_coverage_rejects_a_resealed_plan_with_an_omitted_within_fold():
    plan, within, _ = _partitions(_reference((1, 12, 12, 12, 12)))
    malformed = _with_folds(plan, tuple(fold for fold in plan.folds if fold is not within[0]))
    with pytest.raises(ValueError):
        within_study_holdout_coverage(malformed)


def test_coverage_rejects_repeated_holdouts_even_when_all_five_fold_names_remain():
    plan, within, _ = _partitions(_reference((1, 12, 12, 12, 12)))
    repeated = replace(within[0], fold_id=within[-1].fold_id)
    malformed = _with_folds(
        plan, tuple(repeated if fold is within[-1] else fold for fold in plan.folds)
    )
    with pytest.raises(ValueError):
        within_study_holdout_coverage(malformed)


def test_coverage_rejects_an_unknown_donor_in_a_resealed_within_partition():
    plan, within, _ = _partitions(_reference((1, 12, 12, 12, 12)))
    altered = replace(
        within[0], training_donor_keys=(*within[0].training_donor_keys, "unknown-synthetic-donor")
    )
    malformed = _with_folds(
        plan, tuple(altered if fold is within[0] else fold for fold in plan.folds)
    )
    with pytest.raises(ValueError):
        within_study_holdout_coverage(malformed)


def test_coverage_rejects_a_whole_study_partition_that_loses_a_training_donor():
    plan, _, whole = _partitions(_reference((1, 12, 12, 12, 12)))
    altered = replace(whole[0], training_donor_keys=whole[0].training_donor_keys[1:])
    malformed = _with_folds(
        plan, tuple(altered if fold is whole[0] else fold for fold in plan.folds)
    )
    with pytest.raises(ValueError):
        within_study_holdout_coverage(malformed)


def test_coverage_rejects_within_study_keys_that_do_not_match_the_donor_partition():
    plan, within, _ = _partitions(_reference((1, 12, 12, 12, 12)))
    altered = replace(within[0], training_study_keys=within[0].training_study_keys[1:])
    malformed = _with_folds(
        plan, tuple(altered if fold is within[0] else fold for fold in plan.folds)
    )
    with pytest.raises(ValueError):
        within_study_holdout_coverage(malformed)

from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution.aggregate import (
    AggregateReference,
    DonorLabelAggregate,
)
from glio_proteogen.research.gbmap_deconvolution.splits import (
    LabelFoldSupport,
    build_validation_split_plan,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)


def _reference(donors_by_study: tuple[int, ...] = (10, 10, 10, 10)) -> AggregateReference:
    records: list[DonorLabelAggregate] = []
    for study_index, donor_count in enumerate(donors_by_study):
        for donor_index in range(donor_count):
            donor = f"donor-{study_index}-{donor_index:02d}"
            for label, counts in (
                ("malignant", (16_000, 4_000)),
                ("myeloid", (4_000, 16_000)),
            ):
                records.append(
                    DonorLabelAggregate(
                        donor_key=donor,
                        study_key=f"study-{study_index}",
                        modeled_label=label,
                        source_labels=(label,),
                        cell_count=40,
                        gene_counts=np.asarray(counts, dtype=np.int64),
                        detected_cell_counts=np.asarray((30, 30), dtype=np.int32),
                        total_umis=20_000,
                    )
                )
    return AggregateReference(
        feature_ids=("ENSG1", "ENSG2"),
        gene_symbols=("A", "B"),
        records=tuple(reversed(records)),
        source_file_sha256="sha256:" + "1" * 64,
        source_bytes=8_975_644_082,
        taxonomy_digest="sha256:" + "2" * 64,
        extraction_recipe_digest="sha256:" + "3" * 64,
    )


def test_split_plan_holds_whole_studies_and_donors_without_leakage() -> None:
    reference = _reference()
    plan = build_validation_split_plan(reference)

    assert len(plan.folds) == 9
    assert sum(fold.kind == "whole_study" for fold in plan.folds) == 4
    assert sum(fold.kind == "within_study_donor" for fold in plan.folds) == 5
    assert all(fold.evaluable for fold in plan.folds)
    for fold in plan.folds:
        assert set(fold.training_donor_keys).isdisjoint(fold.held_donor_keys)
        training, held = plan.partition_records(reference, fold.fold_id)
        assert {record.donor_key for record in training} == set(fold.training_donor_keys)
        assert {record.donor_key for record in held} == set(fold.held_donor_keys)
        if fold.kind == "whole_study":
            assert set(fold.training_study_keys).isdisjoint(fold.held_study_keys)
        else:
            assert set(fold.held_study_keys).issubset(fold.training_study_keys)


def test_retained_receipt_contains_no_donor_identifier_or_hash_field() -> None:
    plan = build_validation_split_plan(_reference())

    document = json.dumps(asdict(plan.receipt), sort_keys=True)

    assert "donor-0-00" not in document
    assert "donor_keys" not in document
    assert "donor_digest" not in document
    assert plan.receipt.folds[0].held_study_keys == ("study-0",)
    assert plan.receipt.folds[0].held_donor_count == 10


def test_split_plan_is_input_order_invariant() -> None:
    reference = _reference()
    reordered = AggregateReference(
        feature_ids=reference.feature_ids,
        gene_symbols=reference.gene_symbols,
        records=tuple(reversed(reference.records)),
        source_file_sha256=reference.source_file_sha256,
        source_bytes=reference.source_bytes,
        taxonomy_digest=reference.taxonomy_digest,
        extraction_recipe_digest=reference.extraction_recipe_digest,
    )

    assert build_validation_split_plan(reference) == build_validation_split_plan(reordered)


def test_whole_study_fold_abstains_when_training_has_only_two_studies() -> None:
    plan = build_validation_split_plan(_reference((8, 8, 8)))
    whole_study = tuple(fold for fold in plan.folds if fold.kind == "whole_study")

    assert len(whole_study) == 3
    assert all(not fold.evaluable for fold in whole_study)
    assert all(
        fold.abstention_reasons == ("fewer_than_two_evaluable_labels",) for fold in whole_study
    )
    assert all(
        support.abstention_reasons == ("insufficient_training_studies",)
        for fold in whole_study
        for support in fold.label_support
    )


def test_one_donor_study_is_not_mislabeled_as_within_study_validation() -> None:
    plan = build_validation_split_plan(_reference((1, 8, 8, 8)))
    target = next(
        fold
        for fold in plan.folds
        if fold.kind == "within_study_donor" and "study-0" in fold.held_study_keys
    )

    assert target.evaluable is False
    assert target.abstention_reasons == ("no_same_study_training_donor",)


def test_split_support_rejects_forged_evaluability() -> None:
    with pytest.raises(ValueError, match="fixed evaluability gates"):
        LabelFoldSupport(
            modeled_label="malignant",
            training_usable_donor_count=8,
            training_usable_study_count=3,
            held_usable_donor_count=1,
            held_usable_study_count=1,
            evaluable=False,
            abstention_reasons=(),
        )


def test_split_planner_honors_pre_cancelled_context() -> None:
    cancellation = CancellationContext()
    cancellation.cancel()

    with pytest.raises(InferenceCancelledError, match="cancelled"):
        build_validation_split_plan(_reference(), cancellation=cancellation)

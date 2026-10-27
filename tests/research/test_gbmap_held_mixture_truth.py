"""Independent held-donor count and empirical RNA-mass truth oracles."""

from __future__ import annotations

import json
import pickle
from dataclasses import replace
from fractions import Fraction

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution import selection, training
from glio_proteogen.research.gbmap_deconvolution.aggregate import (
    AggregateReference,
    DonorLabelAggregate,
)
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_deconvolution.splits import build_validation_split_plan
from glio_proteogen.research.gbmap_held_mixture_truth import (
    CallerOwnedMixtureContext,
    EmpiricalMixtureCase,
    HeldMixtureTruth,
    HeldMixtureTruthReceipt,
    LabelTruthCoverage,
    MixtureTruthView,
    UnitCoverageLedger,
    build_held_mixture_truth,
    truth,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

_A = "AC-like"
_B = "B cell"
_C = "Neuron"
_KNOWN = (_A, _B, _C)
_INT64_MAX = int(np.iinfo(np.int64).max)


def _record(donor, study, label, counts, *, cells=40):
    values = np.asarray(counts, dtype=np.int64)
    return DonorLabelAggregate(
        donor_key=donor,
        study_key=study,
        modeled_label=label,
        source_labels=(label,),
        cell_count=cells,
        gene_counts=values,
        detected_cell_counts=np.asarray(values > 0, dtype=np.int32),
        total_umis=sum(map(int, values)),
    )


def _reference(*, held_rows=None, extra_rows=()):
    held_rows = (
        (
            _record("private-held", "study-a", _A, (9_000, 1_000, 90_000)),
            _record("private-held", "study-a", _B, (1_000, 9_000, 0)),
            _record("private-held", "study-a", _C, (0, 0, 20_000), cells=1),
        )
        if held_rows is None
        else held_rows
    )
    training_rows = tuple(
        _record(f"private-train-{study}", f"study-{study}", label, counts)
        for study in ("b", "c")
        for label, counts in (
            (_A, (30_000, 2_000, 8_000)),
            (_B, (1_000, 30_000, 9_000)),
            (_C, (2_000, 3_000, 35_000)),
        )
    )
    return AggregateReference(
        feature_ids=("ENSG-TOY-A", "ENSG-TOY-B", "ENSG-TOY-C"),
        gene_symbols=("TOY-A", "TOY-B", "TOY-C"),
        records=(*training_rows, *held_rows, *extra_rows),
        source_file_sha256="sha256:" + "1" * 64,
        source_bytes=123,
        taxonomy_digest="sha256:" + "2" * 64,
        extraction_recipe_digest="sha256:" + "3" * 64,
    )


def _arguments(reference, *, indices=(0, 1), known=_KNOWN):
    plan = build_validation_split_plan(reference)
    fold = next(item for item in plan.folds if item.held_study_keys == ("study-a",))
    context = CallerOwnedMixtureContext(
        feature_indices=indices,
        known_labels=known,
        feature_order_digest=reference.feature_order_digest,
    )
    return plan, fold, context


def _build(reference=None, *, indices=(0, 1), known=_KNOWN, cancellation=None):
    reference = _reference() if reference is None else reference
    plan, fold, context = _arguments(reference, indices=indices, known=known)
    return build_held_mixture_truth(
        reference,
        plan,
        fold_id=fold.fold_id,
        context=context,
        cancellation=cancellation,
    )


@pytest.mark.parametrize(
    "indices",
    [[], (), (0,), [0, 1], np.asarray((0, 1)), (False, 1), (0.0, 1), (-1, 1), (0, 0)],
)
def test_context_rejects_coerced_or_ambiguous_feature_coordinates(indices):
    with pytest.raises(ValueError):
        CallerOwnedMixtureContext(
            feature_indices=indices,
            known_labels=_KNOWN,
            feature_order_digest="sha256:" + "1" * 64,
        )


@pytest.mark.parametrize(
    "labels", [[_A, _B], (_B, _A), (_A, _A), ("malignant",), ("AC-like ",), (False,)]
)
def test_context_labels_are_exact_canonical_public_labels(labels):
    with pytest.raises(ValueError):
        CallerOwnedMixtureContext(
            feature_indices=(0, 1),
            known_labels=labels,
            feature_order_digest="sha256:" + "1" * 64,
        )


@pytest.mark.parametrize("digest", ["1" * 64, "sha256:" + "A" * 64, "sha256:abc", False])
def test_context_requires_exact_namespaced_feature_order_digest(digest):
    with pytest.raises(ValueError):
        CallerOwnedMixtureContext(
            feature_indices=(0, 1), known_labels=_KNOWN, feature_order_digest=digest
        )


def test_context_feature_limit_is_bounded_without_reading_any_reference():
    context = CallerOwnedMixtureContext(
        feature_indices=tuple(range(512)),
        known_labels=(),
        feature_order_digest="sha256:" + "1" * 64,
    )
    assert len(context.feature_indices) == 512
    assert context.learned_provenance_authenticated is False
    with pytest.raises(ValueError):
        CallerOwnedMixtureContext(
            feature_indices=tuple(range(513)),
            known_labels=(),
            feature_order_digest=context.feature_order_digest,
        )


@pytest.mark.parametrize("claim", [True, 0, 1, None])
def test_caller_owned_context_cannot_claim_learned_provenance_authentication(claim):
    with pytest.raises(ValueError):
        CallerOwnedMixtureContext(
            feature_indices=(0, 1),
            known_labels=_KNOWN,
            feature_order_digest="sha256:" + "1" * 64,
            learned_provenance_authenticated=claim,
        )


@pytest.mark.parametrize("indices", [(0, 3), (0, 10_000)])
def test_selected_feature_coordinates_must_belong_to_the_bound_source_axis(indices):
    with pytest.raises(ValueError):
        _build(indices=indices)


def test_public_known_label_absent_from_training_cannot_be_declared_available():
    with pytest.raises(ValueError):
        _build(known=tuple(sorted((*_KNOWN, "Astrocyte"))))


def test_feature_order_binding_cannot_be_reused_after_a_source_axis_permutation():
    reference = _reference()
    plan, fold, _context = _arguments(reference)
    context = CallerOwnedMixtureContext(
        feature_indices=(0, 1), known_labels=_KNOWN, feature_order_digest="sha256:" + "0" * 64
    )
    with pytest.raises(ValueError):
        build_held_mixture_truth(reference, plan, fold_id=fold.fold_id, context=context)


def test_fixed_plan_cannot_be_reused_after_even_training_counts_change():
    reference = _reference()
    plan, fold, context = _arguments(reference)
    first = next(row for row in reference.records if row.donor_key == "private-train-b")
    changed = replace(
        first,
        gene_counts=np.asarray((40_000, 2_000, 8_000), dtype=np.int64),
        total_umis=50_000,
    )
    replacement = replace(
        reference, records=tuple(changed if row is first else row for row in reference.records)
    )
    with pytest.raises(ValueError):
        build_held_mixture_truth(replacement, plan, fold_id=fold.fold_id, context=context)


@pytest.mark.parametrize("alteration", ["missing_unrequested_fold", "changed_partition"])
def test_complete_original_plan_is_required_even_when_requested_fold_is_unchanged(alteration):
    reference = _reference()
    plan, requested, context = _arguments(reference)
    other = next(fold for fold in plan.folds if fold.fold_id != requested.fold_id)
    if alteration == "missing_unrequested_fold":
        folds = tuple(fold for fold in plan.folds if fold is not other)
    else:
        stolen = other.training_donor_keys[0]
        mutated = replace(
            other,
            training_donor_keys=other.training_donor_keys[1:],
            held_donor_keys=tuple(sorted((*other.held_donor_keys, stolen))),
        )
        folds = tuple(mutated if fold is other else fold for fold in plan.folds)
    altered_plan = replace(
        plan,
        folds=folds,
        receipt=replace(plan.receipt, folds=tuple(fold.deidentified_receipt() for fold in folds)),
    )
    assert (
        next(fold for fold in altered_plan.folds if fold.fold_id == requested.fold_id) == requested
    )
    with pytest.raises(ValueError):
        build_held_mixture_truth(
            reference, altered_plan, fold_id=requested.fold_id, context=context
        )


def test_prior_context_cannot_follow_a_permuted_source_feature_axis():
    reference = _reference()
    _old_plan, _old_fold, old_context = _arguments(reference)
    indices = (2, 0, 1)
    permuted = replace(
        reference,
        feature_ids=tuple(reference.feature_ids[i] for i in indices),
        gene_symbols=tuple(reference.gene_symbols[i] for i in indices),
        records=tuple(
            replace(
                row,
                gene_counts=row.gene_counts[np.asarray(indices)],
                detected_cell_counts=row.detected_cell_counts[np.asarray(indices)],
            )
            for row in reference.records
        ),
    )
    plan, fold, _context = _arguments(permuted)
    with pytest.raises(ValueError):
        build_held_mixture_truth(permuted, plan, fold_id=fold.fold_id, context=old_context)


def test_unknown_fold_does_not_fall_back_to_full_source_or_another_fold():
    reference = _reference()
    plan, _fold, context = _arguments(reference)
    with pytest.raises(ValueError):
        build_held_mixture_truth(reference, plan, fold_id="whole-study-9999", context=context)


def test_already_cancelled_planner_does_not_produce_partial_truth():
    cancellation = CancellationContext()
    cancellation.cancel()
    with pytest.raises(InferenceCancelledError):
        _build(cancellation=cancellation)


def test_expired_planner_deadline_does_not_produce_partial_truth():
    cancellation = CancellationContext(deadline=1.0, clock=lambda: 1.0)
    with pytest.raises(InferenceDeadlineExceededError):
        _build(cancellation=cancellation)


def _label_values(values):
    return dict(zip(PRODUCTION_SOURCE_LABELS, values, strict=True))


def test_source_and_selected_truth_use_distinct_exact_rna_mass_denominators():
    result = _build()
    assert len(result.cases) == 1
    case = result.cases[0]
    np.testing.assert_array_equal(case.selected_counts, (10_000, 10_000))
    assert case.source_total_count_mass == 130_000
    assert case.selected_total_count_mass == 20_000
    assert _label_values(case.source_label_count_mass) == {
        label: {_A: 100_000, _B: 10_000, _C: 20_000}.get(label, 0)
        for label in PRODUCTION_SOURCE_LABELS
    }
    assert _label_values(case.selected_label_count_mass) == {
        label: {_A: 10_000, _B: 10_000}.get(label, 0) for label in PRODUCTION_SOURCE_LABELS
    }
    source_truth = _label_values(case.source_rna_fractions)
    selected_truth = _label_values(case.selected_rna_fractions)
    assert (source_truth[_A], source_truth[_B], source_truth[_C]) == (
        Fraction(10, 13),
        Fraction(1, 13),
        Fraction(2, 13),
    )
    assert (selected_truth[_A], selected_truth[_B], selected_truth[_C]) == (
        Fraction(1, 2),
        Fraction(1, 2),
        Fraction(0),
    )
    assert sum(source_truth.values()) == sum(selected_truth.values()) == 1
    assert case.state == "ready" and case.abstention_reason is None


def test_caller_selected_axis_order_is_preserved_instead_of_sorted_or_reinterpreted():
    case = _build(indices=(2, 0)).cases[0]
    np.testing.assert_array_equal(case.selected_counts, (110_000, 10_000))
    assert case.selected_total_count_mass == 120_000
    truth = _label_values(case.selected_rna_fractions)
    assert (truth[_A], truth[_B], truth[_C]) == (Fraction(33, 40), Fraction(1, 120), Fraction(1, 6))


def test_held_rows_below_fitting_floors_are_retained_in_the_empirical_mixture():
    reference = _reference()
    plan, fold, _context = _arguments(reference)
    _training, held = plan.partition_records(reference, fold.fold_id)
    assert not fold.evaluable
    assert [row.modeled_label for row in held if not row.eligible_for_reference] == [_B, _C]
    case = _build(reference).cases[0]
    assert _label_values(case.source_label_count_mass)[_B] == 10_000
    assert _label_values(case.source_label_count_mass)[_C] == 20_000
    assert int(case.selected_counts.sum()) == 20_000


@pytest.mark.parametrize("omitted", [(_A,), (_C,), _KNOWN])
def test_omission_reclassifies_truth_without_removing_any_observed_counts(omitted):
    case = _build().cases[0]
    before = case.selected_counts.tobytes()
    view = case.reclassify(omitted)
    source_expected = sum({_A: 100_000, _B: 10_000, _C: 20_000}[x] for x in omitted)
    selected_expected = sum({_A: 10_000, _B: 10_000, _C: 0}[x] for x in omitted)
    assert view.selected_counts is case.selected_counts
    assert view.selected_counts.tobytes() == before
    assert view.remaining_known_labels == tuple(label for label in _KNOWN if label not in omitted)
    assert view.source_unknown_count_mass == source_expected
    assert view.selected_unknown_count_mass == selected_expected
    assert view.source_unknown_fraction == Fraction(source_expected, 130_000)
    assert view.selected_unknown_fraction == Fraction(selected_expected, 20_000)


def test_a_source_positive_selected_zero_omission_is_not_mislabeled_absent():
    case = _build().cases[0]
    view = case.reclassify((_C,))
    assert view.source_unknown_count_mass == 20_000
    assert view.source_unknown_fraction == Fraction(2, 13)
    assert view.selected_unknown_count_mass == 0
    assert view.selected_unknown_fraction == 0
    assert _label_values(case.source_rna_fractions)[_C] > 0
    assert _label_values(case.selected_rna_fractions)[_C] == 0


def test_unknown_context_labels_are_conserved_before_any_deliberate_omission():
    case = _build(known=(_A, _B)).cases[0]
    view = case.reclassify()
    assert view.remaining_known_labels == (_A, _B)
    assert view.source_unknown_count_mass == 20_000
    assert view.selected_unknown_count_mass == 0
    assert view.source_unknown_fraction == Fraction(2, 13)


def test_empty_known_axis_is_an_explicit_all_unknown_control():
    case = _build(known=()).cases[0]
    view = case.reclassify()
    assert view.remaining_known_labels == ()
    assert view.source_unknown_count_mass == 130_000
    assert view.selected_unknown_count_mass == 20_000
    assert view.source_unknown_fraction == view.selected_unknown_fraction == 1


@pytest.mark.parametrize("omitted", [[_A], (_B, _A), (_A, _A), ("Astrocyte",), (False,)])
def test_omission_is_a_strict_canonical_subset_of_original_known_labels(omitted):
    with pytest.raises(ValueError):
        _build().cases[0].reclassify(omitted)


def test_changing_training_expression_cannot_change_held_counts_or_empirical_truth():
    original = _reference()
    changed = replace(
        original,
        records=tuple(
            replace(
                row,
                gene_counts=np.asarray((99_000, 111_000, 222_000), dtype=np.int64),
                total_umis=432_000,
            )
            if row.study_key != "study-a"
            else row
            for row in original.records
        ),
    )
    first, second = _build(original).cases[0], _build(changed).cases[0]
    np.testing.assert_array_equal(first.selected_counts, second.selected_counts)
    assert first.source_label_count_mass == second.source_label_count_mass
    assert first.selected_label_count_mass == second.selected_label_count_mass
    assert first.source_rna_fractions == second.source_rna_fractions
    assert first.selected_rna_fractions == second.selected_rna_fractions


def test_unowned_ineligible_donor_in_held_study_is_not_pooled_by_study_membership():
    reference = _reference(
        extra_rows=(_record("private-unassigned", "study-a", _A, (8_000, 1_000, 0), cells=1),)
    )
    plan, fold, _context = _arguments(reference)
    assert "private-unassigned" not in fold.held_donor_keys
    assert all("private-unassigned" not in row.held_donor_keys for row in plan.folds)
    result = _build(reference)
    assert len(result.cases) == 1
    np.testing.assert_array_equal(result.cases[0].selected_counts, (10_000, 10_000))
    assert result.cases[0].source_total_count_mass == 130_000


def test_two_held_donors_produce_two_empirical_units_not_one_study_pool():
    reference = _reference(
        extra_rows=(_record("private-second", "study-a", _A, (30_000, 10_000, 0)),)
    )
    result = _build(reference)
    assert len(result.cases) == 2
    assert sorted(tuple(map(int, row.selected_counts)) for row in result.cases) == [
        (10_000, 10_000),
        (30_000, 10_000),
    ]
    assert sorted(row.source_total_count_mass for row in result.cases) == [40_000, 130_000]


def test_zero_selected_depth_abstains_without_erasing_defined_source_truth():
    rows = tuple(
        _record("private-held", "study-a", label, (0, 0, depth), cells=cells)
        for label, depth, cells in ((_A, 30_000, 40), (_B, 10_000, 40), (_C, 20_000, 1))
    )
    case = _build(_reference(held_rows=rows)).cases[0]
    assert case.state == "abstained"
    assert case.abstention_reason == "zero_selected_count_depth"
    assert case.selected_total_count_mass == 0
    assert case.source_total_count_mass == 60_000
    assert case.selected_rna_fractions is None
    assert _label_values(case.source_rna_fractions)[_A] == Fraction(1, 2)
    view = case.reclassify((_A,))
    assert view.source_unknown_fraction == Fraction(1, 2)
    assert view.selected_unknown_fraction is None
    np.testing.assert_array_equal(view.selected_counts, (0, 0))


def test_int64_boundary_is_exact_and_does_not_pass_through_float_rounding():
    rows = (_record("private-held", "study-a", _A, (_INT64_MAX, 0, 0)),)
    case = _build(_reference(held_rows=rows), known=(_A,)).cases[0]
    assert case.source_total_count_mass == _INT64_MAX
    assert case.selected_total_count_mass == _INT64_MAX
    assert int(case.selected_counts[0]) == _INT64_MAX
    assert _label_values(case.source_rna_fractions)[_A] == 1


def test_pooled_coordinate_overflow_is_rejected_before_int64_array_construction():
    reference = _reference(
        held_rows=(
            _record("private-held", "study-a", _A, (_INT64_MAX, 0, 0)),
            _record("private-held", "study-a", _B, (1, 0, 0)),
        )
    )
    with pytest.raises(ValueError):
        _build(reference, known=(_A,))


def test_cross_feature_depths_above_int64_remain_exact_python_integers_and_fractions():
    reference = _reference(
        held_rows=(
            _record("private-held", "study-a", _A, (_INT64_MAX, 0, 1)),
            _record("private-held", "study-a", _B, (0, 1, 0)),
        )
    )
    case = _build(reference).cases[0]
    assert case.selected_total_count_mass == _INT64_MAX + 1
    assert case.source_total_count_mass == _INT64_MAX + 2
    np.testing.assert_array_equal(case.selected_counts, (_INT64_MAX, 1))
    source = _label_values(case.source_rna_fractions)
    selected = _label_values(case.selected_rna_fractions)
    assert source[_A] == Fraction(_INT64_MAX + 1, _INT64_MAX + 2)
    assert source[_B] == Fraction(1, _INT64_MAX + 2)
    assert selected[_A] == Fraction(_INT64_MAX, _INT64_MAX + 1)
    assert selected[_B] == Fraction(1, _INT64_MAX + 1)
    assert source[_A] < 1 and selected[_A] < 1


def test_held_counts_and_truth_do_not_call_training_selection_or_a_fitter(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("empirical held truth cannot train, select markers or fit a hierarchy")

    monkeypatch.setattr(training, "train_development_candidate", forbidden)
    monkeypatch.setattr(training, "_fit_label", forbidden)
    monkeypatch.setattr(selection, "select_fold_stable_genes", forbidden)
    assert _build().cases[0].source_total_count_mass == 130_000


def test_private_counts_are_immutable_and_cannot_be_made_writeable():
    case = _build().cases[0]
    assert case.selected_counts.dtype == np.dtype(np.int64)
    assert not case.selected_counts.flags.writeable
    with pytest.raises(ValueError):
        case.selected_counts[0] = 0
    with pytest.raises(ValueError):
        case.selected_counts.flags.writeable = True
    with pytest.raises((AttributeError, TypeError)):
        case.selected_total_count_mass = 0


def test_private_wrapper_case_and_view_are_not_json_or_pickle_payloads():
    result = _build()
    case = result.cases[0]
    for private in (result, case, case.reclassify((_A,))):
        with pytest.raises(TypeError):
            json.dumps(private)
        with pytest.raises((TypeError, ValueError)):
            pickle.dumps(private)
        rendered = repr(private)
        assert "private-held" not in rendered
        assert "private-train" not in rendered
        assert "100000" not in rendered
        assert "90000" not in rendered


def test_receipt_closes_all_twenty_labels_and_exposes_coverage_not_fitting_qualification():
    reference = _reference()
    _plan, fold, _context = _arguments(reference)
    receipt = _build(reference).receipt
    assert receipt.fold_id == fold.fold_id
    assert receipt.kind == "whole_study"
    assert receipt.fold_evaluable is False
    assert receipt.source_feature_count == 3
    assert receipt.selected_feature_count == 2
    assert receipt.known_label_count == 3
    assert receipt.held_unit_count == receipt.ready_case_count == 1
    assert receipt.held_raw_record_count == 3
    assert receipt.held_reference_eligible_record_count == 1
    assert receipt.zero_source_depth_case_count == receipt.zero_selected_depth_case_count == 0
    assert tuple(row.modeled_label for row in receipt.labels) == PRODUCTION_SOURCE_LABELS
    labels = {row.modeled_label: row for row in receipt.labels}
    assert {label for label, row in labels.items() if row.known_in_context} == set(_KNOWN)
    assert sum(row.held_record_count for row in receipt.labels) == 3
    assert sum(row.held_reference_eligible_record_count for row in receipt.labels) == 1
    assert labels[_C].held_source_positive_unit_count == 1
    assert labels[_C].held_selected_positive_unit_count == 0
    assert labels[_C].held_source_positive_selected_zero_unit_count == 1
    assert labels["Astrocyte"].held_record_count == 0
    assert labels["Astrocyte"].held_missing_record_unit_count == 1
    assert labels["Astrocyte"].held_source_positive_unit_count == 0


def test_explicit_zero_source_row_is_distinguished_from_a_missing_label_record():
    reference = _reference(
        extra_rows=(_record("private-held", "study-a", "Astrocyte", (0, 0, 0), cells=3),)
    )
    labels = {row.modeled_label: row for row in _build(reference).receipt.labels}
    zero, missing = labels["Astrocyte"], labels["DC"]
    assert zero.held_record_count == 1 and zero.held_source_zero_unit_count == 1
    assert zero.held_missing_record_unit_count == 0
    assert missing.held_record_count == 0 and missing.held_missing_record_unit_count == 1
    assert missing.held_source_positive_unit_count == 0


def test_unassigned_unit_ledger_preserves_wholly_ineligible_source_donors():
    reference = _reference(
        extra_rows=(_record("private-unassigned", "study-a", _A, (8_000, 1_000, 0), cells=1),)
    )
    coverage = _build(reference).receipt.unit_coverage
    assert coverage.source_unit_count == 4
    assert coverage.split_assigned_unit_count == 3
    assert coverage.unassigned_unit_count == 1
    assert coverage.whole_study_held_once_unit_count == 3
    assert coverage.within_study_held_once_unit_count == 0
    assert coverage.within_study_unheld_assigned_unit_count == 3
    assert coverage.source_raw_record_count == 10
    assert coverage.split_assigned_raw_record_count == 9
    assert coverage.unassigned_raw_record_count == 1


def test_public_receipt_is_occurrence_only_and_has_no_private_axes_or_content_seal():
    document = _build().receipt.model_dump(mode="json")
    encoded = json.dumps(document, sort_keys=True)
    for forbidden in (
        "private-held",
        "private-train",
        "ENSG-TOY",
        "TOY-A",
        "donor_key",
        "selected_counts",
        "gene_counts",
        "source_label_count_mass",
        "selected_label_count_mass",
        "aggregate_content_digest",
    ):
        assert forbidden not in encoded
    assert len(document["labels"]) == 20
    assert document["learned_provenance_authenticated"] is False


def test_private_case_discards_donor_and_study_keys_after_grouped_construction():
    case = _build().cases[0]
    assert not hasattr(case, "donor_key")
    assert not hasattr(case, "study_key")


def test_each_within_fold_has_its_own_caller_axis_and_exact_held_donor_pools():
    records = tuple(
        _record(
            f"private-unit-{study}-{donor}",
            f"study-{study}",
            label,
            counts,
            cells=cells,
        )
        for study in range(3)
        for donor in range(2)
        for label, counts, cells in (
            (_A, (20_000 + 2 * study + donor, 10_000, 0), 40),
            (_B, (10_000, 20_000 + 2 * study + donor, 0), 40),
            (_C, (0, 0, 30_000), 1),
        )
    )
    reference = replace(_reference(), records=records)
    plan = build_validation_split_plan(reference)
    folds = tuple(row for row in plan.folds if row.kind == "within_study_donor")
    assert len(folds) == 2
    results = []
    for fold, indices in zip(folds, ((0, 1), (1, 2)), strict=True):
        context = CallerOwnedMixtureContext(
            feature_indices=indices,
            known_labels=_KNOWN,
            feature_order_digest=reference.feature_order_digest,
        )
        results.append(
            build_held_mixture_truth(reference, plan, fold_id=fold.fold_id, context=context)
        )
    assert [tuple(map(int, row.selected_counts)) for row in results[0].cases] == [
        (30_000, 30_000),
        (30_002, 30_002),
        (30_004, 30_004),
    ]
    assert [tuple(map(int, row.selected_counts)) for row in results[1].cases] == [
        (30_001, 30_000),
        (30_003, 30_000),
        (30_005, 30_000),
    ]
    for result in results:
        assert result.receipt.kind == "within_study_donor"
        assert result.receipt.held_unit_count == 3
        assert result.receipt.held_raw_record_count == 9
        assert result.receipt.unit_coverage.within_study_held_once_unit_count == 6
        assert result.receipt.unit_coverage.within_study_unheld_assigned_unit_count == 0
    assert all(_label_values(row.selected_label_count_mass)[_C] == 0 for row in results[0].cases)
    assert all(
        _label_values(row.selected_label_count_mass)[_C] == 30_000 for row in results[1].cases
    )


def test_unmapped_raw_label_is_not_silently_dropped_from_the_twenty_label_truth_axis():
    reference = _reference(
        extra_rows=(_record("private-held", "study-a", "unmapped-private-label", (1, 1, 1)),)
    )
    with pytest.raises(ValueError) as failure:
        _build(reference)
    assert "private-held" not in str(failure.value)
    assert "unmapped-private-label" not in str(failure.value)


def test_public_receipt_round_trips_its_closed_json_schema_without_private_truth():
    receipt = _build().receipt
    encoded = receipt.model_dump_json()
    restored = HeldMixtureTruthReceipt.model_validate_json(encoded)
    assert restored == receipt
    assert restored.model_dump_json() == encoded
    document = json.loads(encoded)
    assert document["learned_provenance_authenticated"] is False
    assert document["model_fitting_performed"] is False
    assert document["inference_performed"] is False
    assert document["calibration_performed"] is False
    assert not any("mass" in key or "fraction" in key for key in document)


@pytest.mark.parametrize(
    "updates",
    [
        {"modeled_label": "unmapped"},
        {"held_record_count": 2},
        {"held_selected_positive_unit_count": 0},
        {"held_reference_eligible_record_count": 2},
        {"held_record_count": True},
    ],
)
def test_public_label_receipt_rejects_nonconserved_or_coerced_occurrences(updates):
    row = _build().receipt.labels[0]
    with pytest.raises(ValueError):
        LabelTruthCoverage.model_validate({**row.model_dump(), **updates})


@pytest.mark.parametrize(
    "field",
    [
        "source_unit_count",
        "source_raw_record_count",
        "whole_study_held_once_unit_count",
        "within_study_held_once_unit_count",
    ],
)
def test_public_unit_ledger_rejects_lost_or_double_counted_units_and_records(field):
    document = _build().receipt.unit_coverage.model_dump()
    document[field] += 1
    with pytest.raises(ValueError):
        UnitCoverageLedger.model_validate(document)


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_public_label",
        "reordered_public_labels",
        "case_states",
        "raw_record_total",
        "eligible_record_total",
        "known_label_total",
        "missing_record_partition",
        "selected_axis_bigger_than_source",
        "more_held_units_than_assigned",
    ],
)
def test_public_full_receipt_rejects_cross_axis_corruption(corruption):
    document = _build().receipt.model_dump(mode="json")
    if corruption == "missing_public_label":
        document["labels"].pop()
    elif corruption == "reordered_public_labels":
        document["labels"][0], document["labels"][1] = document["labels"][1], document["labels"][0]
    elif corruption == "case_states":
        document["ready_case_count"] = 0
    elif corruption == "raw_record_total":
        document["held_raw_record_count"] += 1
    elif corruption == "eligible_record_total":
        document["held_reference_eligible_record_count"] += 1
    elif corruption == "known_label_total":
        document["known_label_count"] -= 1
    elif corruption == "missing_record_partition":
        document["labels"][1]["held_missing_record_unit_count"] = 0
    elif corruption == "selected_axis_bigger_than_source":
        document["selected_feature_count"] = 4
    else:
        document["held_unit_count"] = document["ready_case_count"] = 4
        for label in document["labels"]:
            label["held_missing_record_unit_count"] = 4 - label["held_record_count"]
    with pytest.raises(ValueError):
        HeldMixtureTruthReceipt.model_validate_json(json.dumps(document))


def test_public_receipt_fold_kind_must_match_its_original_fold_identifier():
    document = _build().receipt.model_dump(mode="json")
    document["kind"] = "within_study_donor"
    with pytest.raises(ValueError):
        HeldMixtureTruthReceipt.model_validate_json(json.dumps(document))


@pytest.mark.parametrize(
    "field",
    [
        "learned_provenance_authenticated",
        "model_fitting_performed",
        "inference_performed",
        "calibration_performed",
    ],
)
@pytest.mark.parametrize("claim", [True, 0, 1])
def test_public_receipt_cannot_claim_actions_or_accept_boolean_integer_aliases(field, claim):
    document = _build().receipt.model_dump(mode="json")
    document[field] = claim
    with pytest.raises(ValueError):
        HeldMixtureTruthReceipt.model_validate_json(json.dumps(document))


@pytest.mark.parametrize("field", ["selected_counts", "donor_key", "source_label_count_mass"])
def test_public_receipt_rejects_private_payload_fields(field):
    document = _build().receipt.model_dump(mode="json")
    document[field] = [1, 2]
    with pytest.raises(ValueError):
        HeldMixtureTruthReceipt.model_validate_json(json.dumps(document))


@pytest.mark.parametrize("hook", ["__getstate__", "__reduce__"])
def test_alternate_private_serialization_hooks_fail_closed(hook):
    result = _build()
    for private in (result, result.cases[0], result.cases[0].reclassify()):
        with pytest.raises(TypeError, match="cannot be serialized"):
            getattr(private, hook)()


def test_deleting_private_observations_is_rejected_without_altering_the_case():
    case = _build().cases[0]
    before = case.selected_counts.tobytes()
    with pytest.raises(AttributeError):
        del case.selected_counts
    assert case.selected_counts.tobytes() == before


def _case_arguments():
    case = _build().cases[0]
    return {
        "selected_counts": tuple(map(int, case.selected_counts)),
        "source_mass": case.source_label_count_mass,
        "selected_mass": case.selected_label_count_mass,
        "known_labels": _KNOWN,
    }


@pytest.mark.parametrize(
    "corruption",
    [
        "mutable_counts",
        "wrong_label_axis",
        "negative_count",
        "boolean_count",
        "count_mass_mismatch",
        "selected_exceeds_source",
    ],
)
def test_direct_private_case_constructor_rejects_invalid_count_truth(corruption):
    values = _case_arguments()
    if corruption == "mutable_counts":
        values["selected_counts"] = [10_000, 10_000]
    elif corruption == "wrong_label_axis":
        values["source_mass"] = values["source_mass"][:-1]
    elif corruption == "negative_count":
        values["selected_counts"] = (-1, 20_001)
    elif corruption == "boolean_count":
        values["selected_counts"] = (False, 20_000)
    elif corruption == "count_mass_mismatch":
        values["selected_counts"] = (1, 2)
    else:
        values["selected_counts"] = (100_001, 0)
        values["selected_mass"] = (100_001, *([0] * 19))
    with pytest.raises(ValueError):
        EmpiricalMixtureCase(**values)


def test_direct_zero_source_case_has_undefined_truth_and_cannot_invent_a_denominator():
    case = EmpiricalMixtureCase((0, 0), (0,) * 20, (0,) * 20, ())
    assert case.state == "abstained"
    assert case.abstention_reason == "zero_source_count_depth"
    assert case.source_rna_fractions is case.selected_rna_fractions is None
    view = case.reclassify()
    assert view.source_unknown_count_mass == view.selected_unknown_count_mass == 0
    assert view.source_unknown_fraction is view.selected_unknown_fraction is None


@pytest.mark.parametrize("remaining", [[_A], (_B, _A), (_A, _A), ("Astrocyte",), (False,)])
def test_direct_private_view_cannot_bypass_omission_membership(remaining):
    with pytest.raises(ValueError):
        MixtureTruthView(_build().cases[0], remaining)


def test_direct_private_view_requires_a_genuine_case():
    with pytest.raises(ValueError):
        MixtureTruthView(object(), ())


@pytest.mark.parametrize(
    "corruption", ["mutable_cases", "foreign_case", "missing_case", "foreign_receipt"]
)
def test_direct_collection_rejects_mismatched_cases_and_receipt(corruption):
    result = _build()
    cases, receipt = result.cases, result.receipt
    if corruption == "mutable_cases":
        cases = list(cases)
    elif corruption == "foreign_case":
        cases = (object(),)
    elif corruption == "missing_case":
        cases = ()
    else:
        receipt = receipt.model_dump()
    with pytest.raises(ValueError):
        HeldMixtureTruth(cases, receipt)


@pytest.mark.parametrize("argument", ["reference", "plan", "context", "fold_id", "cancellation"])
def test_planner_rejects_foreign_caller_objects_before_rebuilding_the_plan(monkeypatch, argument):
    reference = _reference()
    plan, fold, context = _arguments(reference)
    arguments = {
        "reference": reference,
        "plan": plan,
        "context": context,
        "fold_id": fold.fold_id,
        "cancellation": None,
    }
    arguments[argument] = object()

    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid caller objects must be rejected before rebuilding source partitions")

    monkeypatch.setattr(truth, "build_validation_split_plan", forbidden)
    with pytest.raises(ValueError):
        build_held_mixture_truth(**arguments)


def test_planner_revalidates_a_caller_constructed_context_instead_of_trusting_its_type():
    reference = _reference()
    plan, fold, context = _arguments(reference)
    unvalidated = context.model_copy(update={"learned_provenance_authenticated": 0})
    with pytest.raises(ValueError):
        build_held_mixture_truth(reference, plan, fold_id=fold.fold_id, context=unvalidated)

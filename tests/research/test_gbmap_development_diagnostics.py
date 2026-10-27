"""Source-independent support, leakage and ordinal-marker attrition oracles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from functools import lru_cache
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.gbmap_deconvolution import hierarchy, selection, training
from glio_proteogen.research.gbmap_deconvolution.aggregate import (
    AggregateReference,
    DonorLabelAggregate,
)
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_deconvolution.splits import build_validation_split_plan
from glio_proteogen.research.gbmap_development_diagnostics import (
    GATE_ORDER,
    DiagnosticsError,
    LabelAttrition,
    MarkerAttrition,
    PartitionAttrition,
    ReferenceAttritionReceipt,
    SupportCounts,
    audit_reference,
)
from glio_proteogen.research.gbmap_development_diagnostics import audit as audit_module
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)

PROFILE = "sha256:" + "d" * 64
LABELS = ("MES-like", "NPC-like")
FLAGS = (
    "model_fitting_performed",
    "inference_performed",
    "model_selection_performed",
    "policy_changed",
    "final_fit_eligibility_established",
    "external_validation_established",
    "biological_absence_established",
    "raw_counts_retained",
    "donor_identifiers_retained",
    "donor_hashes_retained",
    "feature_identities_retained",
)


def _record(
    donor: str, study: str, label: str, counts: np.ndarray[Any, Any], *, cells: int = 100
) -> DonorLabelAggregate:
    return DonorLabelAggregate(
        donor_key=donor,
        study_key=study,
        modeled_label=label,
        source_labels=(label,),
        cell_count=cells,
        gene_counts=counts.astype(np.int64),
        detected_cell_counts=np.minimum(counts, min(80, cells)).astype(np.int32),
        total_umis=sum(int(value) for value in counts),
    )


def _reference(records: tuple[DonorLabelAggregate, ...]) -> AggregateReference:
    features = records[0].gene_counts.size
    return AggregateReference(
        feature_ids=tuple(f"invented-coordinate-{i:04d}" for i in range(features)),
        gene_symbols=(None,) * features,
        records=records,
        source_file_sha256="sha256:" + "a" * 64,
        source_bytes=99,
        taxonomy_digest="sha256:" + "b" * 64,
        extraction_recipe_digest="sha256:" + "c" * 64,
    )


def _marker_reference(
    *,
    labels: tuple[str, ...] = LABELS,
    studies: int = 4,
    donors: int = 4,
    genes_per_label: int = 16,
) -> AggregateReference:
    records = []
    for study in range(studies):
        for donor in range(donors):
            for index, label in enumerate(labels):
                counts = np.ones(len(labels) * genes_per_label, dtype=np.int64)
                counts[index * genes_per_label : (index + 1) * genes_per_label] = 2_000
                records.append(
                    _record(f"invented-donor-{study}-{donor}", f"study-{study}", label, counts)
                )
    return _reference(tuple(records))


@lru_cache(maxsize=1)
def _baseline() -> ReferenceAttritionReceipt:
    return audit_reference(_marker_reference(), development_profile_digest=PROFILE)


def _label(partition: PartitionAttrition, label: str = LABELS[0]) -> Any:
    return next(item for item in partition.labels if item.modeled_label == label)


def _manual_digest(value: Any) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode()
        ).hexdigest()
    )


def _reseal_partition(payload: dict[str, Any]) -> PartitionAttrition:
    payload["partition_digest"] = _manual_digest(
        {key: value for key, value in payload.items() if key != "partition_digest"}
    )
    return PartitionAttrition.model_validate_json(json.dumps(payload))


def test_every_public_label_retained_with_explicit_absence_and_full_source_nulls() -> None:
    receipt = _baseline()
    assert receipt.planning_state == "completed"
    assert len(receipt.partitions) == 9
    full = receipt.partitions[0]
    assert full.kind == "full_source"
    assert full.fold_id is None
    assert full.preparation_state == "not_applicable"
    assert full.prepared_eligible_lineage_count is None
    assert full.prepared_feature_count is None
    for part in receipt.partitions:
        assert tuple(item.modeled_label for item in part.labels) == PRODUCTION_SOURCE_LABELS
    for item in full.labels:
        assert item.held_support is None
        assert item.enters_prepared_fold is None
        if item.modeled_label in LABELS:
            assert item.marker_state == "available"
            assert item.training_support.usable_donor_count == 16
            assert item.training_support.usable_study_count == 4
            assert item.markers.passing_gene_count == 16
        else:
            assert item.training_support.raw_record_count == 0
            assert item.marker_state == "no_eligible_training_records"
            assert item.markers is None


def test_original_preparation_counts_and_lineage_axis_match_without_fitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _marker_reference()
    plan = build_validation_split_plan(reference)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        message = "a diagnostics audit must never fit a hierarchy or candidate"
        raise AssertionError(message)

    for module, name in (
        (hierarchy, "fit_lineage_hierarchy"),
        (training, "fit_lineage_hierarchy"),
        (training, "_fit_label"),
        (training, "_final_fit"),
        (training, "train_development_candidate"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    receipt = audit_reference(reference, development_profile_digest=PROFILE)
    assert len(receipt.partitions) == len(plan.folds) + 1
    for part, fold in zip(receipt.partitions[1:], plan.folds, strict=True):
        prepared = training._prepare_fold(reference, plan, fold, None)
        assert isinstance(prepared, training._PreparedFold)
        assert part.preparation_state == "prepared"
        assert part.prepared_eligible_lineage_count == len(prepared.labels)
        assert part.prepared_feature_count == len(prepared.feature_indices)
        assert (
            tuple(x.modeled_label for x in part.labels if x.enters_prepared_fold) == prepared.labels
        )
        assert part.selector_union_feature_count == 32
    assert all(getattr(receipt, name) is False for name in FLAGS)


def test_cells_counts_and_both_rejections_are_disjoint_at_inclusive_boundaries() -> None:
    base = _marker_reference()
    records = list(base.records)
    for number, (cells, mass) in enumerate(
        ((20, 20_000), (19, 20_000), (20, 19_999), (19, 19_999))
    ):
        counts = np.zeros(32, dtype=np.int64)
        counts[0] = mass
        records.append(
            _record(f"invented-extra-{number}", "study-0", "Endothelial", counts, cells=cells)
        )
    receipt = audit_reference(_reference(tuple(records)), development_profile_digest=PROFILE)
    support = _label(receipt.partitions[0], "Endothelial").training_support
    assert support.raw_record_count == 4
    assert support.eligible_record_count == 1
    assert support.rejected_cells_only_count == 1
    assert support.rejected_counts_only_count == 1
    assert support.rejected_both_count == 1
    assert support.usable_donor_count == support.usable_study_count == 1


def test_comparator_routes_prefer_same_donor_then_same_study_fallback() -> None:
    base = _marker_reference()
    extra = _record("invented-unpaired", "study-0", LABELS[0], base.records[0].gene_counts)
    receipt = audit_reference(
        _reference((*base.records, extra)), development_profile_digest=PROFILE
    )
    routes = _label(receipt.partitions[0]).comparator_routes
    assert routes.same_donor_count == 16
    assert routes.fallback_same_study_count == 1
    assert routes.missing_count == 0
    assert receipt.partitions[0].selection_state == "completed"


def test_missing_comparator_fails_whole_selector_without_partial_metrics() -> None:
    counts = np.full(32, 1000, dtype=np.int64)
    reference = _reference(
        (
            _record("invented-only-a", "study-a", LABELS[0], counts),
            _record("invented-only-b", "study-b", LABELS[1], counts),
        )
    )
    full = audit_reference(reference, development_profile_digest=PROFILE).partitions[0]
    assert full.selection_state == "failed"
    assert full.selection_failure_reason == "missing_training_comparator"
    for label in LABELS:
        assert _label(full, label).comparator_routes.missing_count == 1
    assert all(
        item.markers is None and item.marker_state == "selection_failed" for item in full.labels
    )
    assert full.selector_union_feature_count is None


def test_non_evaluable_splits_do_not_attempt_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    reference = _marker_reference(studies=2, donors=2)
    calls = []
    original = selection._select_fold_stable_genes_precomputed

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs["training_records"])
        return original(*args, **kwargs)

    monkeypatch.setattr(selection, "_select_fold_stable_genes_precomputed", spy)
    receipt = audit_reference(reference, development_profile_digest=PROFILE)
    assert len(calls) == 1  # The full-source diagnostic only.
    for part in receipt.partitions[1:]:
        assert part.selection_state == "not_attempted"
        assert part.preparation_reason == "split_not_evaluable"
        assert part.prepared_eligible_lineage_count == part.prepared_feature_count == 0
        assert all(item.markers is None for item in part.labels)


def test_marker_competition_can_have_real_zero_counts_without_biological_absence_claim() -> None:
    base = _marker_reference()
    identical = np.full(32, 1000, dtype=np.int64)
    reference = _reference(
        tuple(_record(r.donor_key, r.study_key, r.modeled_label, identical) for r in base.records)
    )
    receipt = audit_reference(reference, development_profile_digest=PROFILE)
    for part in receipt.partitions:
        assert part.selection_state == "completed"
        for label in LABELS:
            markers = _label(part, label).markers
            assert markers is not None
            assert markers.individual_pass.strict_winner == 0
            assert markers.passing_gene_count == 0
        if part.kind != "full_source":
            assert part.preparation_state == "abstained"
            assert part.preparation_reason == "fewer_than_two_eligible_lineages"
            assert all(item.enters_prepared_fold is False for item in part.labels)
    assert receipt.biological_absence_established is False


def test_all_twenty_labels_caps_and_union_compete_before_support_filtering() -> None:
    reference = _marker_reference(
        labels=PRODUCTION_SOURCE_LABELS, studies=3, donors=3, genes_per_label=33
    )
    receipt = audit_reference(reference, development_profile_digest=PROFILE)
    full = receipt.partitions[0]
    assert full.selection_state == "completed"
    assert full.selector_union_feature_count == 512
    assert all(item.markers.passing_gene_count == 33 for item in full.labels)
    assert all(item.markers.pre_union_selected_count == 32 for item in full.labels)
    assert sum(item.markers.removed_by_label_cap_count for item in full.labels) == 20
    assert sum(item.markers.removed_by_union_cap_count for item in full.labels) == 128
    assert sum(item.markers.retained_gene_count for item in full.labels) == 512
    # Every whole-study training partition has only six donors per label;
    # the full-source selector was nevertheless not restricted to fit labels.
    assert all(part.selection_state == "not_attempted" for part in receipt.partitions[1:])


def test_held_count_poisoning_cannot_change_that_folds_training_marker_metrics() -> None:
    reference = _marker_reference()
    extreme = np.zeros(32, dtype=np.int64)
    extreme[-1] = 100_000
    poisoned = _reference(
        tuple(
            _record(r.donor_key, r.study_key, r.modeled_label, extreme)
            if r.study_key == "study-0"
            else r
            for r in reference.records
        )
    )
    first = audit_reference(reference, development_profile_digest=PROFILE)
    second = audit_reference(poisoned, development_profile_digest=PROFILE)
    a = next(p for p in first.partitions if p.partition_id == "whole-study-0001")
    b = next(p for p in second.partitions if p.partition_id == "whole-study-0001")
    assert a == b


def test_ordinal_gates_are_inclusive_and_joint_counts_match_original_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _marker_reference(studies=2, donors=2)

    def metrics(label: str, index: Any) -> Any:
        median = np.zeros(32)
        donor = np.ones(32)
        study = np.ones(32)
        detection = np.ones(32)
        if label == LABELS[0]:
            median.fill(-1)
            median[:7] = (0.75, 0.75, np.nextafter(0.75, -np.inf), 1, 1, 1, 1)
            donor[0] = 0.70
            donor[3] = np.nextafter(0.70, -np.inf)
            study[0] = 0.75
            study[4] = np.nextafter(0.75, -np.inf)
            detection[0] = 0.10
            detection[5] = np.nextafter(0.10, -np.inf)
        else:
            median[:7] = (0.25, 0.75, 0, 0, 0, 0, np.nextafter(0.5, np.inf))
        return selection._LabelMetrics(
            records=index.by_label[label],
            median=median,
            donor_stability=donor,
            study_stability=study,
            detection=detection,
            mad=np.zeros(32),
        )

    monkeypatch.setattr(selection, "_label_metrics", metrics)
    full = audit_reference(reference, development_profile_digest=PROFILE).partitions[0]
    markers = _label(full).markers
    assert tuple(getattr(markers.cumulative_pass, name) for name in GATE_ORDER) == (
        6,
        5,
        4,
        3,
        2,
        1,
    )
    assert markers.passing_gene_count == markers.retained_gene_count == 1


def test_gate_denominator_uses_only_original_admitted_indices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        selection, "model_eligible_feature_indices", lambda *args, **kwargs: (0, 1, 16, 17)
    )
    receipt = audit_reference(_marker_reference(), development_profile_digest=PROFILE)
    assert receipt.source_feature_count == 32
    assert receipt.admitted_feature_count == 4
    assert receipt.excluded_feature_count == 28
    for label in LABELS:
        assert _label(receipt.partitions[0], label).markers.passing_gene_count == 2


@pytest.mark.parametrize("mode", ["none", "one"])
def test_no_invented_plan_when_usable_label_axis_is_insufficient(mode: str) -> None:
    counts = np.full(32, 1000 if mode == "one" else 1, dtype=np.int64)
    receipt = audit_reference(
        _reference((_record("invented-donor", "study", LABELS[0], counts),)),
        development_profile_digest=PROFILE,
    )
    assert receipt.planning_state == "not_available"
    assert len(receipt.partitions) == 1
    assert receipt.planning_failure_reason == (
        "no_eligible_records" if mode == "none" else "fewer_than_two_usable_labels"
    )
    assert receipt.partitions[0].selection_failure_reason == (
        "no_eligible_training_records"
        if mode == "none"
        else "fewer_than_two_usable_training_labels"
    )


def test_training_study_without_eligible_record_is_explicit_selection_failure() -> None:
    base = _marker_reference()
    ineligible = _record(
        "invented-ineligible-only", "isolated-study", "Endothelial", np.ones(32, dtype=np.int64)
    )
    full = audit_reference(
        _reference((*base.records, ineligible)), development_profile_digest=PROFILE
    ).partitions[0]
    assert full.selection_failure_reason == "training_study_without_eligible_record"
    assert all(item.markers is None for item in full.labels)


def test_canonical_seals_have_independent_json_oracle_and_roundtrip() -> None:
    receipt = _baseline()
    payload = receipt.model_dump(mode="json")
    assert receipt.receipt_digest == _manual_digest(
        {k: v for k, v in payload.items() if k != "receipt_digest"}
    )
    for part in payload["partitions"]:
        assert part["partition_digest"] == _manual_digest(
            {k: v for k, v in part.items() if k != "partition_digest"}
        )
    assert ReferenceAttritionReceipt.model_validate_json(canonical_json_bytes(receipt)) == receipt
    with pytest.raises(ValidationError):
        ReferenceAttritionReceipt.model_validate(payload)  # Python lists remain forbidden.


@pytest.mark.parametrize("name", FLAGS)
@pytest.mark.parametrize("bad", [0, True, "false"])
def test_fixed_false_flags_cannot_be_coerced(name: str, bad: object) -> None:
    payload = _baseline().model_dump(mode="json")
    payload[name] = bad
    with pytest.raises(ValidationError):
        ReferenceAttritionReceipt.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("bad", [None, True, 1, "d" * 64, "sha256:" + "x" * 64])
def test_development_profile_binding_must_be_exact_digest(bad: Any) -> None:
    with pytest.raises(ValueError):
        audit_reference(_marker_reference(), development_profile_digest=bad)


def test_invalid_reference_labels_and_cancellation_are_rejected() -> None:
    with pytest.raises(DiagnosticsError, match="exact aggregate"):
        audit_reference(None, development_profile_digest=PROFILE)  # type: ignore[arg-type]
    with pytest.raises(DiagnosticsError, match="nonpublic"):
        audit_reference(
            _marker_reference(labels=("invented-label", LABELS[1])),
            development_profile_digest=PROFILE,
        )
    with pytest.raises(DiagnosticsError, match="cancellation"):
        audit_reference(_marker_reference(), development_profile_digest=PROFILE, cancellation=True)  # type: ignore[arg-type]
    context = CancellationContext()
    context.cancel()
    with pytest.raises(InferenceCancelledError):
        audit_reference(
            _marker_reference(), development_profile_digest=PROFILE, cancellation=context
        )


def test_support_bool_and_nonconserved_partitions_are_rejected() -> None:
    payload = _label(_baseline().partitions[0]).training_support.model_dump(mode="python")
    payload["eligible_record_count"] = True
    with pytest.raises(ValidationError):
        SupportCounts.model_validate(payload)
    payload["eligible_record_count"] = 15
    with pytest.raises(ValidationError, match="conserve"):
        SupportCounts.model_validate(payload)


def test_resealed_impossible_marginal_intersection_is_rejected() -> None:
    payload = _label(_baseline().partitions[0]).markers.model_dump(mode="python")
    payload["individual_pass"] = dict.fromkeys(GATE_ORDER, 32)
    payload["cumulative_pass"] = dict.fromkeys(GATE_ORDER, 16)
    payload["cumulative_pass"]["strict_winner"] = 32
    with pytest.raises(ValidationError, match="conserve"):
        MarkerAttrition.model_validate(payload)


@pytest.mark.parametrize(
    "mutation",
    ["missing_comparator", "split_support", "false_preparation", "union_count", "label_axis"],
)
def test_resealed_cross_stage_forgery_is_rejected(mutation: str) -> None:
    payload = _baseline().partitions[1].model_dump(mode="json")
    target = next(x for x in payload["labels"] if x["modeled_label"] == LABELS[0])
    if mutation == "missing_comparator":
        target["comparator_routes"]["same_donor_count"] -= 1
        target["comparator_routes"]["missing_count"] += 1
    elif mutation == "split_support":
        target["split_label_evaluable"] = False
    elif mutation == "false_preparation":
        payload["selection_state"] = "failed"
        payload["selection_failure_reason"] = "selector_failed"
        payload["selector_union_feature_count"] = None
        for item in payload["labels"]:
            item["markers"] = None
            item["marker_state"] = "selection_failed"
    elif mutation == "union_count":
        payload["prepared_feature_count"] -= 1
    else:
        payload["labels"] = payload["labels"][:-1]
    with pytest.raises(ValidationError):
        _reseal_partition(payload)


def test_original_selector_reconstruction_disagreement_is_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = selection._select_fold_stable_genes_precomputed

    def inconsistent(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        group = replace(
            result.by_label[0], passing_gene_count=result.by_label[0].passing_gene_count + 1
        )
        return replace(result, by_label=(group, *result.by_label[1:]))

    monkeypatch.setattr(selection, "_select_fold_stable_genes_precomputed", inconsistent)
    with pytest.raises(DiagnosticsError, match="gate reconstruction"):
        audit_reference(_marker_reference(), development_profile_digest=PROFILE)


def test_unexpected_selector_errors_are_not_reclassified(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(*_args: object, **_kwargs: object) -> None:
        message = "invented unexpected failure"
        raise RuntimeError(message)

    monkeypatch.setattr(selection, "_select_fold_stable_genes_precomputed", unexpected)
    with pytest.raises(RuntimeError):
        audit_reference(_marker_reference(), development_profile_digest=PROFILE)


def test_public_receipt_contains_no_private_reference_identifiers_or_content_seal() -> None:
    receipt = _baseline()
    text = canonical_json_bytes(receipt).decode()
    assert "aggregate_content_digest" not in text
    assert "training_donor_keys" not in text
    assert "invented-donor" not in text
    assert '"study-0"' not in text
    assert "invented-coordinate" not in text
    assert "gene_counts" not in text
    assert "detected_cell_counts" not in text
    assert receipt.development_profile_binding == "caller_supplied_not_authenticated"
    with pytest.raises(ValidationError):
        receipt.model_fitting_performed = True  # type: ignore[misc]


def test_known_selector_failure_is_explicit_sanitized_and_matches_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        message = "invented private details must not enter receipt"
        raise ValueError(message)

    monkeypatch.setattr(selection, "_select_fold_stable_genes_precomputed", fail)
    monkeypatch.setattr(training, "_select_fold_stable_genes_precomputed", fail)
    receipt = audit_reference(_marker_reference(), development_profile_digest=PROFILE)
    assert receipt.partitions[0].selection_failure_reason == "selector_failed"
    for part in receipt.partitions[1:]:
        assert part.selection_state == "failed"
        assert part.preparation_reason == "stable_gene_selection_failed"
        assert part.prepared_eligible_lineage_count == part.prepared_feature_count == 0
        assert all(item.markers is None for item in part.labels)
    assert "invented private details" not in canonical_json_bytes(receipt).decode()


def test_preparation_failure_keeps_computed_selection_and_unavailable_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise ValueError

    monkeypatch.setattr(training, "_prepare_fold", fail)
    receipt = audit_reference(_marker_reference(), development_profile_digest=PROFILE)
    for part in receipt.partitions[1:]:
        assert part.selection_state == "completed"
        assert part.preparation_state == "failed"
        assert part.preparation_reason == "preparation_failed"
        assert part.prepared_eligible_lineage_count is None
        assert part.prepared_feature_count is None
        assert all(item.enters_prepared_fold is False for item in part.labels)
        assert _label(part).markers is not None


@pytest.mark.parametrize(
    "mode", ["wrong_axis", "false_selection_abstention", "prepared_without_selection"]
)
def test_original_preparation_inconsistency_is_fatal(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    reference = _marker_reference()
    plan = build_validation_split_plan(reference)
    genuine = training._prepare_fold(reference, plan, plan.folds[0], None)
    assert isinstance(genuine, training._PreparedFold)
    if mode == "wrong_axis":
        altered = replace(genuine, labels=genuine.labels[:1])
    elif mode == "false_selection_abstention":
        altered = training._AbstainedFold(plan.folds[0], "stable_gene_selection_failed")
    else:
        altered = genuine

        def selector_fail(*_args: object, **_kwargs: object) -> None:
            raise ValueError

        monkeypatch.setattr(selection, "_select_fold_stable_genes_precomputed", selector_fail)
    monkeypatch.setattr(training, "_prepare_fold", lambda *_args, **_kwargs: altered)
    with pytest.raises(DiagnosticsError):
        audit_reference(reference, development_profile_digest=PROFILE)


def test_missing_plan_cannot_be_used_as_training_partition() -> None:
    reference = _marker_reference()
    plan = build_validation_split_plan(reference)
    cache = selection._build_reference_selection_cache(reference)
    with pytest.raises(DiagnosticsError, match="exact split plan"):
        audit_module._partition(reference, cache, None, plan.folds[0], None)


@pytest.mark.parametrize("bound", ["MAX_FEATURES", "MAX_RECORDS"])
def test_reference_size_bounds_reject_before_any_selection(
    monkeypatch: pytest.MonkeyPatch, bound: str
) -> None:
    monkeypatch.setattr(audit_module, bound, 1)
    with pytest.raises(DiagnosticsError, match="bounds"):
        audit_reference(_marker_reference(), development_profile_digest=PROFILE)


def test_cancellation_after_selector_stops_before_receipt_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = CancellationContext()
    original = selection._select_fold_stable_genes_precomputed

    def cancel_after(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        context.cancel()
        return result

    monkeypatch.setattr(selection, "_select_fold_stable_genes_precomputed", cancel_after)
    with pytest.raises(InferenceCancelledError):
        audit_reference(
            _marker_reference(), development_profile_digest=PROFILE, cancellation=context
        )


@pytest.mark.parametrize(
    "mutation",
    ["unknown_label", "incomplete_nulls", "available_without_targets", "no_targets_with_records"],
)
def test_closed_label_states_reject_false_support_and_applicability(mutation: str) -> None:
    full = _baseline().partitions[0]
    target = _label(full).model_dump(mode="json")
    if mutation == "unknown_label":
        target["modeled_label"] = "invented-private-label"
    elif mutation == "incomplete_nulls":
        target["enters_prepared_fold"] = False
    elif mutation == "available_without_targets":
        absent = _label(full, "AC-like").model_dump(mode="json")
        absent["marker_state"] = "available"
        absent["markers"] = target["markers"]
        target = absent
    else:
        target["marker_state"] = "no_eligible_training_records"
        target["markers"] = None
    with pytest.raises(ValidationError):
        LabelAttrition.model_validate_json(json.dumps(target))


@pytest.mark.parametrize(
    "mutation",
    [
        "kind_identifier",
        "family_identifier",
        "held_applicability",
        "missing_selector_reason",
        "missing_union",
        "wrong_marker_state",
        "wrong_union",
        "too_many_strict_winners",
        "full_preparation",
        "fold_not_applicable",
        "unprepared_reason_null",
        "unprepared_entry",
        "failed_dimensions",
        "skipped_wrong_selection",
        "failure_wrong_selection",
        "lineage_count",
        "small_union_dimensions",
        "unknown_abstention_semantics",
        "partition_seal",
    ],
)
def test_partition_resealing_does_not_allow_stage_forgery(  # noqa: C901, PLR0912, PLR0915 - closed adversarial cases.
    mutation: str,
) -> None:
    payload = _baseline().partitions[1].model_dump(mode="json")
    if mutation == "kind_identifier":
        payload["fold_id"] = "whole-study-9999"
    elif mutation == "family_identifier":
        payload["kind"] = "within_study_donor"
    elif mutation == "held_applicability":
        target = payload["labels"][0]
        target["held_support"] = target["split_label_evaluable"] = target[
            "enters_prepared_fold"
        ] = None
    elif mutation == "missing_selector_reason":
        payload["selection_failure_reason"] = "selector_failed"
    elif mutation == "missing_union":
        payload["selector_union_feature_count"] = None
    elif mutation == "wrong_marker_state":
        payload["labels"][0]["marker_state"] = "not_attempted"
    elif mutation == "wrong_union":
        payload["selector_union_feature_count"] += 1
    elif mutation == "too_many_strict_winners":
        for target in payload["labels"]:
            if target["markers"] is not None:
                target["markers"]["individual_pass"]["strict_winner"] = 32
                target["markers"]["cumulative_pass"]["strict_winner"] = 32
    elif mutation == "full_preparation":
        payload = _baseline().partitions[0].model_dump(mode="json")
        payload["prepared_feature_count"] = 32
    elif mutation == "fold_not_applicable":
        payload["preparation_state"] = "not_applicable"
    else:
        payload["preparation_state"] = "abstained"
        payload["preparation_reason"] = "fewer_than_two_eligible_lineages"
        for target in payload["labels"]:
            target["enters_prepared_fold"] = False
        if mutation == "unprepared_reason_null":
            payload["preparation_reason"] = None
        elif mutation == "unprepared_entry":
            next(x for x in payload["labels"] if x["modeled_label"] == LABELS[0])[
                "enters_prepared_fold"
            ] = True
        elif mutation == "failed_dimensions":
            payload["preparation_state"] = "failed"
            payload["preparation_reason"] = "preparation_failed"
        elif mutation == "skipped_wrong_selection":
            payload["preparation_reason"] = "split_not_evaluable"
        elif mutation == "failure_wrong_selection":
            payload["preparation_reason"] = "stable_gene_selection_failed"
        elif mutation == "lineage_count":
            payload["prepared_eligible_lineage_count"] = 0
        elif mutation == "small_union_dimensions":
            payload["preparation_reason"] = "selected_marker_union_too_small"
        elif mutation == "unknown_abstention_semantics":
            payload["preparation_reason"] = "preparation_failed"
        elif mutation == "partition_seal":
            payload = _baseline().partitions[1].model_dump(mode="json")
            payload["partition_digest"] = "sha256:" + "0" * 64
            with pytest.raises(ValidationError, match="seal"):
                PartitionAttrition.model_validate_json(json.dumps(payload))
            return
    with pytest.raises(ValidationError):
        _reseal_partition(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        "policy",
        "gate_order",
        "feature_conservation",
        "no_partitions",
        "duplicate_partition",
        "missing_full_source",
        "planning_reason",
        "planning_status",
        "fold_order",
        "denominator",
        "seal",
    ],
)
def test_reference_resealing_cannot_change_closed_policy_or_axis(  # noqa: C901 - closed adversarial cases.
    mutation: str,
) -> None:
    payload = _baseline().model_dump(mode="json")
    if mutation == "policy":
        payload["policy_digest"] = "sha256:" + "0" * 64
    elif mutation == "gate_order":
        payload["ordinal_gate_order"] = list(reversed(GATE_ORDER))
    elif mutation == "feature_conservation":
        payload["source_feature_count"] += 1
    elif mutation == "no_partitions":
        payload["partitions"] = []
    elif mutation == "duplicate_partition":
        payload["partitions"].append(payload["partitions"][-1])
    elif mutation == "missing_full_source":
        payload["partitions"] = payload["partitions"][1:]
    elif mutation == "planning_reason":
        payload["planning_failure_reason"] = "no_eligible_records"
    elif mutation == "planning_status":
        payload["planning_state"] = "not_available"
        payload["planning_failure_reason"] = "no_eligible_records"
    elif mutation == "fold_order":
        payload["partitions"][1:] = reversed(payload["partitions"][1:])
    elif mutation == "denominator":
        payload["admitted_feature_count"] = 31
        payload["excluded_feature_count"] = 1
    else:
        payload["source_bytes"] += 1
    if mutation != "seal":
        payload["receipt_digest"] = _manual_digest(
            {k: v for k, v in payload.items() if k != "receipt_digest"}
        )
    with pytest.raises(ValidationError):
        ReferenceAttritionReceipt.model_validate_json(json.dumps(payload))

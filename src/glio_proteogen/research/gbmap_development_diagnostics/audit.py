"""Pure, non-fitting reconstruction of the original GBmap selection stages."""

from __future__ import annotations

from typing import Literal, cast

import numpy as np
from pydantic import TypeAdapter

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import Sha256Digest
from glio_proteogen.research.gbmap_deconvolution import selection, training
from glio_proteogen.research.gbmap_deconvolution.aggregate import (
    MIN_CELLS_PER_DONOR_LABEL,
    MIN_STABLE_GENES_PER_LINEAGE,
    MIN_UMIS_PER_DONOR_LABEL,
    AggregateReference,
    DonorLabelAggregate,
    donor_label_is_eligible,
)
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_deconvolution.splits import (
    TransientValidationFold,
    ValidationSplitPlan,
    build_validation_split_plan,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .contracts import (
    GATE_ORDER,
    MAX_FEATURES,
    MAX_RECORDS,
    POLICY_DIGEST,
    ComparatorCounts,
    DiagnosticsError,
    GatePassCounts,
    LabelAttrition,
    MarkerAttrition,
    PartitionAttrition,
    PreparationReason,
    ReferenceAttritionReceipt,
    SelectorFailure,
    SupportCounts,
)


def _support(records: tuple[DonorLabelAggregate, ...], label: str) -> SupportCounts:
    targets = tuple(record for record in records if record.modeled_label == label)
    eligible = tuple(record for record in targets if donor_label_is_eligible(record))
    return SupportCounts(
        raw_record_count=len(targets),
        raw_study_count=len({record.study_key for record in targets}),
        eligible_record_count=len(eligible),
        rejected_cells_only_count=sum(
            record.cell_count < MIN_CELLS_PER_DONOR_LABEL
            and record.total_umis >= MIN_UMIS_PER_DONOR_LABEL
            for record in targets
        ),
        rejected_counts_only_count=sum(
            record.cell_count >= MIN_CELLS_PER_DONOR_LABEL
            and record.total_umis < MIN_UMIS_PER_DONOR_LABEL
            for record in targets
        ),
        rejected_both_count=sum(
            record.cell_count < MIN_CELLS_PER_DONOR_LABEL
            and record.total_umis < MIN_UMIS_PER_DONOR_LABEL
            for record in targets
        ),
        usable_donor_count=len({record.donor_key for record in eligible}),
        usable_study_count=len({record.study_key for record in eligible}),
    )


def _comparator_routes(
    usable: tuple[DonorLabelAggregate, ...],
) -> dict[str, ComparatorCounts]:
    by_donor: dict[str, set[str]] = {}
    by_study: dict[str, set[str]] = {}
    counts = {label: [0, 0, 0] for label in PRODUCTION_SOURCE_LABELS}
    for target in usable:
        by_donor.setdefault(target.donor_key, set()).add(target.modeled_label)
        by_study.setdefault(target.study_key, set()).add(target.modeled_label)
    for target in usable:
        label = target.modeled_label
        if by_donor[target.donor_key] - {label}:
            counts[label][0] += 1
        elif by_study[target.study_key] - {label}:
            # With no other label in this donor, every other-label record in
            # the same study necessarily belongs to another donor.
            counts[label][1] += 1
        else:
            counts[label][2] += 1
    return {
        label: ComparatorCounts(
            same_donor_count=value[0], fallback_same_study_count=value[1], missing_count=value[2]
        )
        for label, value in counts.items()
    }


def _selection_failure_reason(
    records: tuple[DonorLabelAggregate, ...],
    usable: tuple[DonorLabelAggregate, ...],
    routes: dict[str, ComparatorCounts],
) -> SelectorFailure:
    if not usable:
        return "no_eligible_training_records"
    if {record.study_key for record in records} != {record.study_key for record in usable}:
        return "training_study_without_eligible_record"
    if len({record.modeled_label for record in usable}) < 2:
        return "fewer_than_two_usable_training_labels"
    if any(value.missing_count for value in routes.values()):
        return "missing_training_comparator"
    return "selector_failed"


def _marker_counts(
    cache: selection._ReferenceSelectionCache,
    usable: tuple[DonorLabelAggregate, ...],
    selected: selection.StableGeneSelection,
    cancellation: CancellationContext | None,
) -> dict[str, MarkerAttrition]:
    """Reconstruct gate counts from the unchanged private metric definitions."""

    index = selection._fold_selection_index(usable, cache)
    labels = tuple(group.modeled_label for group in selected.by_label)
    metrics = {}
    for label in labels:
        checkpoint(cancellation)
        metrics[label] = selection._label_metrics(label, index)
    median_matrix = np.stack(tuple(metrics[label].median for label in labels), axis=0)
    admitted = np.asarray(cache.eligible_feature_indices, dtype=np.int64)
    result: dict[str, MarkerAttrition] = {}
    for position, group in enumerate(selected.by_label):
        checkpoint(cancellation)
        others = np.asarray(tuple(i for i in range(len(labels)) if i != position), dtype=np.int64)
        other_max = np.max(median_matrix[others, :], axis=0)
        values = metrics[group.modeled_label]
        masks = (
            values.median[admitted] > other_max[admitted],
            values.median[admitted] >= selection.MIN_MEDIAN_LOG2_ENRICHMENT,
            values.donor_stability[admitted] >= selection.MIN_DONOR_POSITIVE_FRACTION,
            values.study_stability[admitted] >= selection.MIN_STUDY_POSITIVE_MEDIAN_FRACTION,
            values.detection[admitted] >= selection.MIN_MEDIAN_DETECTION_FRACTION,
            (values.median[admitted] - other_max[admitted]) >= selection.MIN_LABEL_MARGIN,
        )
        cumulative = np.ones(admitted.shape, dtype=np.bool_)
        individual_counts: dict[str, int] = {}
        cumulative_counts: dict[str, int] = {}
        for name, mask in zip(GATE_ORDER, masks, strict=True):
            individual_counts[name] = int(np.count_nonzero(mask))
            cumulative &= mask
            cumulative_counts[name] = int(np.count_nonzero(cumulative))
        if cumulative_counts["margin"] != group.passing_gene_count:
            raise DiagnosticsError("diagnostic gate reconstruction differs from original selector")
        result[group.modeled_label] = MarkerAttrition(
            admitted_feature_count=len(admitted),
            individual_pass=GatePassCounts.model_validate(individual_counts),
            cumulative_pass=GatePassCounts.model_validate(cumulative_counts),
            passing_gene_count=group.passing_gene_count,
            pre_union_selected_count=group.pre_union_selected_count,
            retained_gene_count=len(group.genes),
            removed_by_label_cap_count=group.passing_gene_count - group.pre_union_selected_count,
            removed_by_union_cap_count=group.pre_union_selected_count - len(group.genes),
        )
    if sum(item.retained_gene_count for item in result.values()) != len(
        selected.union_feature_indices
    ):
        raise DiagnosticsError("diagnostic union differs from original selector")
    return result


def _partition(  # noqa: PLR0915 - explicit closed stage reconciliation.
    reference: AggregateReference,
    cache: selection._ReferenceSelectionCache,
    plan: ValidationSplitPlan | None,
    fold: TransientValidationFold | None,
    cancellation: CancellationContext | None,
) -> PartitionAttrition:
    checkpoint(cancellation)
    if fold is None:
        training_records = reference.records
        held_records = None
    else:
        if plan is None:
            raise DiagnosticsError("a validation partition requires its exact split plan")
        training_records, held_records = plan.partition_records(reference, fold.fold_id)
    usable = tuple(record for record in training_records if donor_label_is_eligible(record))
    routes = _comparator_routes(usable)
    selected = None
    marker_counts: dict[str, MarkerAttrition] = {}
    selection_state: Literal["completed", "not_attempted", "failed"] = "not_attempted"
    selector_failure = None
    if fold is None or fold.evaluable:
        try:
            selected = selection._select_fold_stable_genes_precomputed(
                reference, cache, training_records=training_records
            )
        except ValueError:
            selection_state = "failed"
            selector_failure = _selection_failure_reason(training_records, usable, routes)
        else:
            selection_state = "completed"
            marker_counts = _marker_counts(cache, usable, selected, cancellation)

    preparation_state: Literal["prepared", "abstained", "failed", "not_applicable"] = (
        "not_applicable"
    )
    preparation_reason: PreparationReason | None = None
    eligible_count = feature_count = None
    prepared_labels: tuple[str, ...] = ()
    if fold is not None:
        try:
            prepared = training._prepare_fold(
                reference, cast("ValidationSplitPlan", plan), fold, cancellation, cache
            )
        except ValueError:
            preparation_state = "failed"
            preparation_reason = "preparation_failed"
        else:
            if isinstance(prepared, training._PreparedFold):
                if selected is None:
                    raise DiagnosticsError("prepared fold requires completed original selection")
                expected_labels = tuple(
                    item.modeled_label
                    for item in fold.label_support
                    if item.evaluable
                    and selected.stable_gene_counts.get(item.modeled_label, 0)
                    >= MIN_STABLE_GENES_PER_LINEAGE
                )
                expected_features = training._selected_features(selected, expected_labels)
                if (
                    prepared.labels != expected_labels
                    or prepared.feature_indices != expected_features
                ):
                    raise DiagnosticsError("diagnostic preparation differs from original trainer")
                preparation_state = "prepared"
                prepared_labels = prepared.labels
                eligible_count = len(prepared.labels)
                feature_count = len(prepared.feature_indices)
            else:
                preparation_state = "abstained"
                preparation_reason = cast("PreparationReason", prepared.reason)
                eligible_count = prepared.eligible_lineage_count
                feature_count = prepared.selected_feature_count
                if (
                    fold.evaluable
                    and selected is None
                    and prepared.reason != "stable_gene_selection_failed"
                ) or (selected is not None and prepared.reason == "stable_gene_selection_failed"):
                    raise DiagnosticsError("diagnostic selection and original preparation disagree")

    support = {} if fold is None else {item.modeled_label: item for item in fold.label_support}
    label_records = []
    for label in PRODUCTION_SOURCE_LABELS:
        train_support = _support(training_records, label)
        if selection_state == "not_attempted":
            marker_state = "not_attempted"
        elif selection_state == "failed":
            marker_state = "selection_failed"
        else:
            marker_state = "available" if label in marker_counts else "no_eligible_training_records"
        label_records.append(
            LabelAttrition(
                modeled_label=label,
                training_support=train_support,
                held_support=None if held_records is None else _support(held_records, label),
                comparator_routes=routes[label],
                marker_state=cast(
                    "Literal['available', 'not_attempted', 'selection_failed', 'no_eligible_training_records']",
                    marker_state,
                ),
                markers=marker_counts.get(label),
                split_label_evaluable=(
                    None if fold is None else label in support and support[label].evaluable
                ),
                enters_prepared_fold=None if fold is None else label in prepared_labels,
            )
        )
    payload = {
        "partition_id": "full-source" if fold is None else fold.fold_id,
        "fold_id": None if fold is None else fold.fold_id,
        "kind": "full_source" if fold is None else fold.kind,
        "selection_state": selection_state,
        "selection_failure_reason": selector_failure,
        "preparation_state": preparation_state,
        "preparation_reason": preparation_reason,
        "prepared_eligible_lineage_count": eligible_count,
        "prepared_feature_count": feature_count,
        "selector_union_feature_count": (
            None if selected is None else len(selected.union_feature_indices)
        ),
        "labels": tuple(label_records),
    }
    return PartitionAttrition.model_validate(
        {**payload, "partition_digest": sha256_digest(payload)}
    )


def audit_reference(
    reference: AggregateReference,
    *,
    development_profile_digest: str,
    cancellation: CancellationContext | None = None,
) -> ReferenceAttritionReceipt:
    """Audit all public labels using existing split/selection/preparation only.

    ``development_profile_digest`` is a caller-supplied provenance binding;
    this pure API does not authenticate it or perform any source I/O.  Fold
    preparation is checked without invoking any hierarchy or final fit.
    Full-source metrics are descriptive development diagnostics only.
    """

    if type(reference) is not AggregateReference:
        raise DiagnosticsError("diagnostics require an exact aggregate reference")
    if cancellation is not None and type(cancellation) is not CancellationContext:
        raise DiagnosticsError("diagnostics require an exact cancellation context")
    TypeAdapter(Sha256Digest).validate_python(development_profile_digest, strict=True)
    if len(reference.feature_ids) > MAX_FEATURES or len(reference.records) > MAX_RECORDS:
        raise DiagnosticsError("aggregate reference exceeds diagnostic bounds")
    if set(reference.modeled_labels) - set(PRODUCTION_SOURCE_LABELS):
        raise DiagnosticsError("aggregate reference contains a nonpublic modeled label")
    checkpoint(cancellation)
    cache = selection._build_reference_selection_cache(reference)
    usable = tuple(record for record in reference.records if donor_label_is_eligible(record))
    planning_failure: Literal["no_eligible_records", "fewer_than_two_usable_labels"] | None = None
    if not usable:
        planning_failure = "no_eligible_records"
    elif len({record.modeled_label for record in usable}) < 2:
        planning_failure = "fewer_than_two_usable_labels"
    plan = (
        None
        if planning_failure is not None
        else build_validation_split_plan(reference, cancellation=cancellation)
    )
    partitions = [_partition(reference, cache, plan, None, cancellation)]
    if plan is not None:
        for fold in plan.folds:
            checkpoint(cancellation)
            partitions.append(_partition(reference, cache, plan, fold, cancellation))
    payload = {
        "profile_id": "gbmap-development-diagnostics/1.0.0",
        "policy_digest": POLICY_DIGEST,
        "development_profile_id": "gbmap-dm-composition/0.1.0-dev",
        "development_profile_digest": development_profile_digest,
        "development_profile_binding": "caller_supplied_not_authenticated",
        "source_file_sha256": reference.source_file_sha256,
        "source_bytes": reference.source_bytes,
        "taxonomy_digest": reference.taxonomy_digest,
        "extraction_recipe_digest": reference.extraction_recipe_digest,
        "feature_order_digest": reference.feature_order_digest,
        "source_feature_count": len(reference.feature_ids),
        "admitted_feature_count": len(cache.eligible_feature_indices),
        "excluded_feature_count": len(reference.feature_ids) - len(cache.eligible_feature_indices),
        "planning_state": "completed" if plan is not None else "not_available",
        "planning_failure_reason": planning_failure,
        "ordinal_gate_order": GATE_ORDER,
        "partitions": tuple(partitions),
        "model_fitting_performed": False,
        "inference_performed": False,
        "model_selection_performed": False,
        "policy_changed": False,
        "final_fit_eligibility_established": False,
        "external_validation_established": False,
        "biological_absence_established": False,
        "raw_counts_retained": False,
        "donor_identifiers_retained": False,
        "donor_hashes_retained": False,
        "feature_identities_retained": False,
    }
    return ReferenceAttritionReceipt.model_validate(
        {**payload, "receipt_digest": sha256_digest(payload)}
    )


__all__ = ["audit_reference"]

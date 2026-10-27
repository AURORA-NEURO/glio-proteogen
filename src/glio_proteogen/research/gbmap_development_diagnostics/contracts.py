"""Closed aggregate-only support and marker attrition contracts.

An ordinal gate decomposition is descriptive.  It neither attributes causes
nor establishes final-fit eligibility, held prediction quality or absence of
a biological population.  The development-profile digest is caller-bound.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, Self

from pydantic import Field, ValidationInfo, field_validator, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.gbmap_deconvolution.aggregate import (
    MIN_CELLS_PER_DONOR_LABEL,
    MIN_DONORS_PER_LINEAGE,
    MIN_STABLE_GENES_PER_LINEAGE,
    MIN_STUDIES_PER_LINEAGE,
    MIN_UMIS_PER_DONOR_LABEL,
)
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_deconvolution.selection import (
    MAX_GENES_PER_LABEL,
    MAX_UNION_GENES,
    MIN_DONOR_POSITIVE_FRACTION,
    MIN_LABEL_MARGIN,
    MIN_MEDIAN_DETECTION_FRACTION,
    MIN_MEDIAN_LOG2_ENRICHMENT,
    MIN_STUDY_POSITIVE_MEDIAN_FRACTION,
    SELECTION_PSEUDOCOUNT,
)
from glio_proteogen.research.gbmap_deconvolution.splits import WITHIN_STUDY_SPLIT_POLICY_ID

PROFILE_ID: Final = "gbmap-development-diagnostics/1.0.0"
MAX_FEATURES: Final = 20_000
MAX_RECORDS: Final = 81_920
MAX_PARTITIONS: Final = 1_025
GATE_ORDER: Final = (
    "strict_winner",
    "enrichment",
    "donor_positive",
    "study_positive",
    "detection",
    "margin",
)
POLICY_DIGEST: Final = sha256_digest(
    {
        "profile_id": PROFILE_ID,
        "source_labels": PRODUCTION_SOURCE_LABELS,
        "within_study_split_policy_id": WITHIN_STUDY_SPLIT_POLICY_ID,
        "minimum_cells": MIN_CELLS_PER_DONOR_LABEL,
        "minimum_count_mass": MIN_UMIS_PER_DONOR_LABEL,
        "minimum_donors": MIN_DONORS_PER_LINEAGE,
        "minimum_studies": MIN_STUDIES_PER_LINEAGE,
        "minimum_stable_genes": MIN_STABLE_GENES_PER_LINEAGE,
        "selection_pseudocount": SELECTION_PSEUDOCOUNT,
        "ordinal_gate_order": GATE_ORDER,
        "strict_winner_comparison": ">",
        "inclusive_thresholds": (
            MIN_MEDIAN_LOG2_ENRICHMENT,
            MIN_DONOR_POSITIVE_FRACTION,
            MIN_STUDY_POSITIVE_MEDIAN_FRACTION,
            MIN_MEDIAN_DETECTION_FRACTION,
            MIN_LABEL_MARGIN,
        ),
        "maximum_genes_per_label": MAX_GENES_PER_LABEL,
        "maximum_union_genes": MAX_UNION_GENES,
        "final_fit_eligibility_established": False,
    }
)

Count = Annotated[int, Field(ge=0, le=MAX_RECORDS)]
FeatureCount = Annotated[int, Field(ge=0, le=MAX_FEATURES)]
PartitionId = Annotated[
    str, Field(pattern=r"^(?:full-source|(?:whole-study|within-study-donor)-[0-9]{4})$")
]
SelectorFailure = Literal[
    "no_eligible_training_records",
    "training_study_without_eligible_record",
    "fewer_than_two_usable_training_labels",
    "missing_training_comparator",
    "selector_failed",
]
PreparationReason = Literal[
    "split_not_evaluable",
    "stable_gene_selection_failed",
    "fewer_than_two_eligible_lineages",
    "selected_marker_union_too_small",
    "preparation_failed",
]


class DiagnosticsError(ValueError):
    """Sanitized inconsistency of the aggregate diagnostic boundary."""


class _StrictFrozen(FrozenModel):
    # Container before validators break strict JSON tuple decoding.  These
    # explicit scalar-only names preserve both strictness and JSON roundtrips.
    @field_validator(
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
        mode="before",
        check_fields=False,
    )
    @classmethod
    def exact_false(cls, value: object, info: ValidationInfo) -> object:
        if (
            info.field_name is not None
            and cls.model_fields[info.field_name].default is False
            and value is not False
        ):
            raise ValueError("diagnostic permission flags require exact false")
        return value


class SupportCounts(_StrictFrozen):
    raw_record_count: Count
    raw_study_count: Count
    eligible_record_count: Count
    rejected_cells_only_count: Count
    rejected_counts_only_count: Count
    rejected_both_count: Count
    usable_donor_count: Count
    usable_study_count: Count

    @model_validator(mode="after")
    def conserve_support(self) -> Self:
        if (
            self.raw_record_count
            != self.eligible_record_count
            + self.rejected_cells_only_count
            + self.rejected_counts_only_count
            + self.rejected_both_count
            or self.usable_donor_count != self.eligible_record_count
            or not 0 <= self.usable_study_count <= self.raw_study_count <= self.raw_record_count
            or self.usable_study_count > self.usable_donor_count
            or (self.raw_record_count == 0) != (self.raw_study_count == 0)
            or (self.usable_donor_count == 0) != (self.usable_study_count == 0)
        ):
            raise ValueError("support counts do not conserve disjoint eligibility states")
        return self


class ComparatorCounts(_StrictFrozen):
    same_donor_count: Count
    fallback_same_study_count: Count
    missing_count: Count


class GatePassCounts(_StrictFrozen):
    strict_winner: FeatureCount
    enrichment: FeatureCount
    donor_positive: FeatureCount
    study_positive: FeatureCount
    detection: FeatureCount
    margin: FeatureCount


class MarkerAttrition(_StrictFrozen):
    admitted_feature_count: FeatureCount
    individual_pass: GatePassCounts
    cumulative_pass: GatePassCounts
    passing_gene_count: FeatureCount
    pre_union_selected_count: Annotated[int, Field(ge=0, le=MAX_GENES_PER_LABEL)]
    retained_gene_count: Annotated[int, Field(ge=0, le=MAX_GENES_PER_LABEL)]
    removed_by_label_cap_count: FeatureCount
    removed_by_union_cap_count: Annotated[int, Field(ge=0, le=MAX_GENES_PER_LABEL)]

    @model_validator(mode="after")
    def conserve_gates_and_caps(self) -> Self:
        individual = tuple(getattr(self.individual_pass, name) for name in GATE_ORDER)
        cumulative = tuple(getattr(self.cumulative_pass, name) for name in GATE_ORDER)
        if (
            any(value > self.admitted_feature_count for value in individual)
            or any(a > b for a, b in zip(cumulative, individual, strict=True))
            or cumulative != tuple(sorted(cumulative, reverse=True))
            or cumulative[0] != individual[0]
            or individual[-1] > individual[0]
            or any(
                after < max(0, before + marginal - self.admitted_feature_count)
                for before, marginal, after in zip(
                    cumulative[:-1], individual[1:], cumulative[1:], strict=True
                )
            )
            or cumulative[-1] != self.passing_gene_count
            or self.pre_union_selected_count != min(self.passing_gene_count, MAX_GENES_PER_LABEL)
            or self.retained_gene_count > self.pre_union_selected_count
            or self.removed_by_label_cap_count
            != self.passing_gene_count - self.pre_union_selected_count
            or self.removed_by_union_cap_count
            != self.pre_union_selected_count - self.retained_gene_count
        ):
            raise ValueError("marker attrition does not conserve gates, label cap and union cap")
        return self


class LabelAttrition(_StrictFrozen):
    modeled_label: str
    training_support: SupportCounts
    held_support: SupportCounts | None
    comparator_routes: ComparatorCounts
    marker_state: Literal[
        "available", "not_attempted", "selection_failed", "no_eligible_training_records"
    ]
    markers: MarkerAttrition | None
    split_label_evaluable: bool | None
    enters_prepared_fold: bool | None

    @model_validator(mode="after")
    def validate_label(self) -> Self:
        if self.modeled_label not in PRODUCTION_SOURCE_LABELS:
            raise ValueError("only the fixed public source labels are permitted")
        routes = self.comparator_routes
        if (
            routes.same_donor_count + routes.fallback_same_study_count + routes.missing_count
            != self.training_support.eligible_record_count
            or (self.marker_state == "available") != (self.markers is not None)
            or (
                self.marker_state == "available"
                and self.training_support.eligible_record_count == 0
            )
            or (self.marker_state == "available" and routes.missing_count != 0)
            or (
                self.marker_state == "no_eligible_training_records"
                and self.training_support.eligible_record_count != 0
            )
        ):
            raise ValueError("label state or comparator routes do not conserve training targets")
        if (self.held_support is None) != (self.split_label_evaluable is None) or (
            self.held_support is None
        ) != (self.enters_prepared_fold is None):
            raise ValueError("full-source held and preparation fields must be explicit nulls")
        if self.held_support is not None:
            expected_support = (
                self.training_support.usable_donor_count >= MIN_DONORS_PER_LINEAGE
                and self.training_support.usable_study_count >= MIN_STUDIES_PER_LINEAGE
                and self.held_support.usable_donor_count > 0
                and self.held_support.usable_study_count > 0
            )
            if self.split_label_evaluable is not expected_support or (
                self.enters_prepared_fold is True
                and (
                    not expected_support
                    or self.markers is None
                    or self.markers.retained_gene_count < MIN_STABLE_GENES_PER_LINEAGE
                )
            ):
                raise ValueError("split-label support or entry does not match the fixed floors")
        return self


class PartitionAttrition(_StrictFrozen):
    partition_id: PartitionId
    fold_id: PartitionId | None
    kind: Literal["full_source", "whole_study", "within_study_donor"]
    selection_state: Literal["completed", "not_attempted", "failed"]
    selection_failure_reason: SelectorFailure | None
    preparation_state: Literal["prepared", "abstained", "failed", "not_applicable"]
    preparation_reason: PreparationReason | None
    prepared_eligible_lineage_count: Annotated[int, Field(ge=0, le=20)] | None
    prepared_feature_count: Annotated[int, Field(ge=0, le=MAX_UNION_GENES)] | None
    selector_union_feature_count: Annotated[int, Field(ge=0, le=MAX_UNION_GENES)] | None
    labels: tuple[LabelAttrition, ...]
    partition_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_partition(self) -> Self:  # noqa: PLR0915 - closed cross-stage consistency rules.
        if tuple(label.modeled_label for label in self.labels) != PRODUCTION_SOURCE_LABELS:
            raise ValueError("every partition must retain the complete public 20-label axis")
        full = self.kind == "full_source"
        if full != (self.partition_id == "full-source") or (
            self.fold_id != (None if full else self.partition_id)
        ):
            raise ValueError("partition kind and identifier disagree")
        if not full and not self.partition_id.startswith(
            "whole-study-" if self.kind == "whole_study" else "within-study-donor-"
        ):
            raise ValueError("fold identifier and validation family disagree")
        if any((label.held_support is None) != full for label in self.labels):
            raise ValueError("held support is applicable only to validation partitions")
        if (self.selection_state == "failed") != (self.selection_failure_reason is not None):
            raise ValueError("selector failure requires an explicit closed reason")
        if self.selection_state == "completed":
            if self.selector_union_feature_count is None or any(
                label.marker_state not in ("available", "no_eligible_training_records")
                for label in self.labels
            ):
                raise ValueError("completed selection must retain all available marker counts")
            if sum(label.marker_state == "available" for label in self.labels) < 2 or any(
                label.comparator_routes.missing_count != 0 for label in self.labels
            ):
                raise ValueError("completed selection requires two labels and complete comparators")
            if self.selector_union_feature_count != sum(
                label.markers.retained_gene_count
                for label in self.labels
                if label.markers is not None
            ):
                raise ValueError("selector-wide union does not conserve label retention")
            available = tuple(label.markers for label in self.labels if label.markers is not None)
            if (
                len({item.admitted_feature_count for item in available}) != 1
                or sum(item.individual_pass.strict_winner for item in available)
                > available[0].admitted_feature_count
            ):
                raise ValueError("strict winners cannot exceed the shared admitted feature axis")
        elif self.selector_union_feature_count is not None or any(
            label.markers is not None
            or label.marker_state
            != ("not_attempted" if self.selection_state == "not_attempted" else "selection_failed")
            for label in self.labels
        ):
            raise ValueError("unavailable selector metrics must remain explicit nulls")
        if full:
            if (
                self.preparation_state != "not_applicable"
                or self.preparation_reason is not None
                or self.prepared_eligible_lineage_count is not None
                or self.prepared_feature_count is not None
                or self.selection_state == "not_attempted"
            ):
                raise ValueError("full-source markers cannot establish fold or final eligibility")
        else:
            if self.preparation_state == "not_applicable":
                raise ValueError("validation preparation must have an explicit state")
            if self.preparation_state == "prepared":
                if (
                    self.selection_state != "completed"
                    or self.preparation_reason is not None
                    or self.prepared_eligible_lineage_count is None
                    or self.prepared_feature_count is None
                    or min(self.prepared_eligible_lineage_count, self.prepared_feature_count) < 2
                    or self.prepared_eligible_lineage_count
                    != sum(label.enters_prepared_fold is True for label in self.labels)
                    or any(
                        label.enters_prepared_fold
                        is not (
                            label.split_label_evaluable is True
                            and label.markers is not None
                            and label.markers.retained_gene_count >= MIN_STABLE_GENES_PER_LINEAGE
                        )
                        for label in self.labels
                    )
                    or self.prepared_feature_count
                    != sum(
                        label.markers.retained_gene_count
                        for label in self.labels
                        if label.enters_prepared_fold is True and label.markers is not None
                    )
                ):
                    raise ValueError("prepared fold dimensions and lineage axis disagree")
            elif self.preparation_reason is None:
                raise ValueError("unprepared fold requires an explicit reason")
            elif any(label.enters_prepared_fold is not False for label in self.labels):
                raise ValueError("an unprepared fold cannot contain entering lineages")
            if self.preparation_state == "failed":
                if (
                    self.preparation_reason != "preparation_failed"
                    or self.prepared_eligible_lineage_count is not None
                    or self.prepared_feature_count is not None
                ):
                    raise ValueError("failed preparation dimensions must remain unavailable")
            elif self.preparation_state == "abstained":
                if self.preparation_reason == "split_not_evaluable":
                    if self.selection_state != "not_attempted" or (
                        self.prepared_eligible_lineage_count,
                        self.prepared_feature_count,
                    ) != (0, 0):
                        raise ValueError("skipped split must preserve the original zero dimensions")
                elif self.preparation_reason == "stable_gene_selection_failed":
                    if self.selection_state != "failed" or (
                        self.prepared_eligible_lineage_count,
                        self.prepared_feature_count,
                    ) != (0, 0):
                        raise ValueError(
                            "selector failure must preserve original preparation status"
                        )
                elif self.preparation_reason == "fewer_than_two_eligible_lineages":
                    eligible = sum(
                        label.split_label_evaluable is True
                        and label.markers is not None
                        and label.markers.retained_gene_count >= MIN_STABLE_GENES_PER_LINEAGE
                        for label in self.labels
                    )
                    if (
                        self.selection_state != "completed"
                        or eligible >= 2
                        or self.prepared_eligible_lineage_count != eligible
                        or self.prepared_feature_count != 0
                    ):
                        raise ValueError("lineage-floor abstention does not match marker support")
                elif self.preparation_reason == "selected_marker_union_too_small":
                    if (
                        self.selection_state != "completed"
                        or self.prepared_eligible_lineage_count is None
                        or self.prepared_eligible_lineage_count < 2
                        or self.prepared_feature_count is None
                        or self.prepared_feature_count >= 2
                    ):
                        raise ValueError("small-union abstention has inconsistent dimensions")
                else:
                    raise ValueError("abstention reason does not describe an original preparation")
        if self.partition_digest != sha256_digest(
            self.model_dump(mode="json", exclude={"partition_digest"})
        ):
            raise ValueError("partition canonical seal does not match")
        return self


class ReferenceAttritionReceipt(_StrictFrozen):
    profile_id: Literal["gbmap-development-diagnostics/1.0.0"] = PROFILE_ID
    policy_digest: Sha256Digest
    development_profile_id: Literal["gbmap-dm-composition/0.1.0-dev"] = (
        "gbmap-dm-composition/0.1.0-dev"
    )
    development_profile_digest: Sha256Digest
    development_profile_binding: Literal["caller_supplied_not_authenticated"] = (
        "caller_supplied_not_authenticated"
    )
    source_file_sha256: Sha256Digest
    source_bytes: Annotated[int, Field(gt=0)]
    taxonomy_digest: Sha256Digest
    extraction_recipe_digest: Sha256Digest
    feature_order_digest: Sha256Digest
    source_feature_count: Annotated[int, Field(ge=1, le=MAX_FEATURES)]
    admitted_feature_count: FeatureCount
    excluded_feature_count: FeatureCount
    planning_state: Literal["completed", "not_available"]
    planning_failure_reason: Literal["no_eligible_records", "fewer_than_two_usable_labels"] | None
    ordinal_gate_order: tuple[str, ...] = GATE_ORDER
    partitions: tuple[PartitionAttrition, ...]
    model_fitting_performed: Literal[False] = False
    inference_performed: Literal[False] = False
    model_selection_performed: Literal[False] = False
    policy_changed: Literal[False] = False
    final_fit_eligibility_established: Literal[False] = False
    external_validation_established: Literal[False] = False
    biological_absence_established: Literal[False] = False
    raw_counts_retained: Literal[False] = False
    donor_identifiers_retained: Literal[False] = False
    donor_hashes_retained: Literal[False] = False
    feature_identities_retained: Literal[False] = False
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_reference_receipt(self) -> Self:
        if (
            self.policy_digest != POLICY_DIGEST
            or self.ordinal_gate_order != GATE_ORDER
            or self.source_feature_count
            != self.admitted_feature_count + self.excluded_feature_count
            or not 1 <= len(self.partitions) <= MAX_PARTITIONS
            or self.partitions[0].partition_id != "full-source"
            or len({part.partition_id for part in self.partitions}) != len(self.partitions)
            or any(part.kind == "full_source" for part in self.partitions[1:])
            or (self.planning_state == "not_available")
            != (self.planning_failure_reason is not None)
            or (self.planning_state == "not_available" and len(self.partitions) != 1)
            or (self.planning_state == "completed" and len(self.partitions) < 2)
            or tuple(part.partition_id for part in self.partitions[1:])
            != tuple(sorted(part.partition_id for part in self.partitions[1:]))
        ):
            raise ValueError("reference provenance, axis or planning state is inconsistent")
        if any(
            label.markers is not None
            and label.markers.admitted_feature_count != self.admitted_feature_count
            for part in self.partitions
            for label in part.labels
        ):
            raise ValueError("all marker denominators must use the admitted feature axis")
        if self.receipt_digest != sha256_digest(
            self.model_dump(mode="json", exclude={"receipt_digest"})
        ):
            raise ValueError("reference attrition canonical seal does not match")
        return self


__all__ = [
    "GATE_ORDER",
    "POLICY_DIGEST",
    "PROFILE_ID",
    "ComparatorCounts",
    "DiagnosticsError",
    "GatePassCounts",
    "LabelAttrition",
    "MarkerAttrition",
    "PartitionAttrition",
    "ReferenceAttritionReceipt",
    "SupportCounts",
]

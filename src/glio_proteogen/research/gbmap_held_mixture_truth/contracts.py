"""Count-only coverage of empirical held-donor reference mixtures."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS

Count = Annotated[int, Field(ge=0)]


class MixtureTruthError(ValueError):
    """Sanitized failure of a private empirical mixture boundary."""


class CallerOwnedMixtureContext(FrozenModel):
    """A caller axis/label declaration, never proof of learned fitting."""

    feature_indices: tuple[int, ...] = Field(min_length=2, max_length=512, repr=False)
    known_labels: tuple[str, ...] = Field(max_length=20)
    feature_order_digest: Sha256Digest
    learned_provenance_authenticated: Literal[False] = False

    @field_validator("learned_provenance_authenticated", mode="before")
    @classmethod
    def exact_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("caller-owned learned provenance is not authenticated")
        return value

    @model_validator(mode="after")
    def validate_axis(self) -> Self:
        if (
            any(index < 0 for index in self.feature_indices)
            or len(set(self.feature_indices)) != len(self.feature_indices)
            or self.known_labels != tuple(sorted(set(self.known_labels)))
            or set(self.known_labels) - set(PRODUCTION_SOURCE_LABELS)
        ):
            raise ValueError("context requires unique coordinates and sorted public labels")
        return self


class LabelTruthCoverage(FrozenModel):
    modeled_label: str
    known_in_context: bool
    held_record_count: Count
    held_reference_eligible_record_count: Count
    held_source_positive_unit_count: Count
    held_selected_positive_unit_count: Count
    held_source_positive_selected_zero_unit_count: Count
    held_source_zero_unit_count: Count
    held_missing_record_unit_count: Count

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if (
            self.modeled_label not in PRODUCTION_SOURCE_LABELS
            or self.held_record_count
            != self.held_source_positive_unit_count + self.held_source_zero_unit_count
            or self.held_source_positive_unit_count
            != self.held_selected_positive_unit_count
            + self.held_source_positive_selected_zero_unit_count
            or self.held_reference_eligible_record_count > self.held_record_count
        ):
            raise ValueError("public label coverage does not conserve observed states")
        return self


class UnitCoverageLedger(FrozenModel):
    source_unit_count: Count
    split_assigned_unit_count: Count
    unassigned_unit_count: Count
    whole_study_held_once_unit_count: Count
    within_study_held_once_unit_count: Count
    within_study_unheld_assigned_unit_count: Count
    source_raw_record_count: Count
    split_assigned_raw_record_count: Count
    unassigned_raw_record_count: Count

    @model_validator(mode="after")
    def conserve_assignment(self) -> Self:
        if (
            self.source_unit_count != self.split_assigned_unit_count + self.unassigned_unit_count
            or self.source_raw_record_count
            != self.split_assigned_raw_record_count + self.unassigned_raw_record_count
            or self.whole_study_held_once_unit_count != self.split_assigned_unit_count
            or self.within_study_held_once_unit_count + self.within_study_unheld_assigned_unit_count
            != self.split_assigned_unit_count
        ):
            raise ValueError("source-unit assignment does not conserve the original split universe")
        return self


class HeldMixtureTruthReceipt(FrozenModel):
    """Coverage occurrences only; no case/count vector or learned artifact."""

    fold_id: str = Field(pattern=r"^(?:whole-study|within-study-donor)-[0-9]{4}$")
    kind: Literal["whole_study", "within_study_donor"]
    fold_evaluable: bool
    source_feature_count: Annotated[int, Field(ge=1)]
    selected_feature_count: Annotated[int, Field(ge=2, le=512)]
    known_label_count: Annotated[int, Field(ge=0, le=20)]
    held_unit_count: Count
    held_raw_record_count: Count
    held_reference_eligible_record_count: Count
    ready_case_count: Count
    zero_source_depth_case_count: Count
    zero_selected_depth_case_count: Count
    labels: tuple[LabelTruthCoverage, ...]
    unit_coverage: UnitCoverageLedger
    learned_provenance_authenticated: Literal[False] = False
    model_fitting_performed: Literal[False] = False
    inference_performed: Literal[False] = False
    calibration_performed: Literal[False] = False

    @field_validator(
        "learned_provenance_authenticated",
        "model_fitting_performed",
        "inference_performed",
        "calibration_performed",
        mode="before",
    )
    @classmethod
    def exact_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("empirical count truth cannot authenticate fitting or inference")
        return value

    @model_validator(mode="after")
    def conserve_coverage(self) -> Self:
        if (
            tuple(item.modeled_label for item in self.labels) != PRODUCTION_SOURCE_LABELS
            or self.held_unit_count
            != self.ready_case_count
            + self.zero_source_depth_case_count
            + self.zero_selected_depth_case_count
            or self.held_raw_record_count != sum(item.held_record_count for item in self.labels)
            or self.held_reference_eligible_record_count
            != sum(item.held_reference_eligible_record_count for item in self.labels)
            or self.known_label_count != sum(item.known_in_context for item in self.labels)
            or any(
                item.held_record_count + item.held_missing_record_unit_count != self.held_unit_count
                for item in self.labels
            )
            or self.selected_feature_count > self.source_feature_count
            or self.held_unit_count > self.unit_coverage.split_assigned_unit_count
            or not self.fold_id.startswith(
                "whole-study-" if self.kind == "whole_study" else "within-study-donor-"
            )
        ):
            raise ValueError("held mixture coverage does not conserve its fixed axes")
        return self

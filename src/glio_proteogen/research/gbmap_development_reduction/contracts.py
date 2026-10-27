"""Closed aggregate contracts for complete GBmap development-task reduction.

These mirrors deliberately import no tool, source reader or fitting runtime.
Canonical seals prove internal consistency, never issuer authenticity or a
fresh reconstruction of the private training matrices.
"""

from __future__ import annotations

import math
from typing import Annotated, Final, Literal, Self

from pydantic import Field, ValidationInfo, field_validator, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS

REDUCTION_PROFILE_ID: Final = "gbmap-complete-development-reduction/1.0.0"
LINEAGE_POLICY_ID: Final = "gbmap-final-lineage-validation-coverage/1.0.0"
SHRINKAGE_GRID: Final = (0.1, 1.0, 10.0, 100.0)
MINIMUM_WHOLE_STUDY_FOLDS: Final = 3
MINIMUM_WITHIN_STUDY_DONOR_FOLDS: Final = 5
MAX_FOLDS: Final = 1_024
MAX_TASKS: Final = MAX_FOLDS * len(SHRINKAGE_GRID) * len(PRODUCTION_SOURCE_LABELS)
FoldId = Annotated[str, Field(pattern=r"^(?:whole-study|within-study-donor)-[0-9]{4}$")]
ValidationKind = Literal["whole_study", "within_study_donor"]
PreparationReason = Literal[
    "split_not_evaluable",
    "stable_gene_selection_failed",
    "fewer_than_two_eligible_lineages",
    "selected_marker_union_too_small",
]
TaskFailureReason = Literal[
    "hierarchy_did_not_converge",
    "hierarchy_fit_failed",
    "hierarchy_trace_invalid",
    "no_positive_held_marker_counts",
]
FoldReason = Literal[
    "split_not_evaluable",
    "stable_gene_selection_failed",
    "fewer_than_two_eligible_lineages",
    "selected_marker_union_too_small",
    "hierarchy_did_not_converge",
    "hierarchy_fit_failed",
    "no_positive_held_marker_counts",
]


class ReductionError(ValueError):
    """Sanitized failure of a closed aggregate binding or completeness rule."""


def _fold_kind(fold_id: str, kind: ValidationKind) -> None:
    prefix = "whole-study-" if kind == "whole_study" else "within-study-donor-"
    if not fold_id.startswith(prefix):
        raise ValueError("fold identifier and validation family do not agree")


def _strict_float(value: object) -> object:
    if value is not None and (type(value) is not float or not math.isfinite(value)):
        raise ValueError("an exact finite float or explicit null is required")
    return value


class _StrictFrozen(FrozenModel):
    # Before validators on container fields discard Pydantic's strict JSON
    # tuple context. Touch only these closed scalar permission/scope fields.
    @field_validator(
        "source_admission_granted",
        "final_model_fitted",
        "model_artifact_emitted",
        "production_artifact_permitted",
        "runtime_mount_permitted",
        "public_http_mounted",
        "public_cli_mounted",
        "source_path_retained",
        "donor_identifiers_retained",
        "donor_hashes_retained",
        "donor_profiles_retained",
        "feature_identities_retained",
        "raw_material_retained",
        "numerical_or_marker_success_established",
        "model_selection_performed",
        "full_source_support_rechecked",
        "final_fit_eligibility_established",
        "selection_score_is_unbiased_performance_estimate",
        "mixture_accuracy_established",
        "external_validation_established",
        "private_training_matrix_reconstruction_performed",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def exact_fixed_false_values(cls, value: object, info: ValidationInfo) -> object:
        if (
            info.field_name is not None
            and cls.model_fields[info.field_name].default is False
            and value is not False
        ):
            raise ValueError("fixed false fields cannot be coerced")
        return value


class _Flags(_StrictFrozen):
    source_admission_granted: Literal[False] = False
    final_model_fitted: Literal[False] = False
    model_artifact_emitted: Literal[False] = False
    production_artifact_permitted: Literal[False] = False
    runtime_mount_permitted: Literal[False] = False
    public_http_mounted: Literal[False] = False
    public_cli_mounted: Literal[False] = False
    source_path_retained: Literal[False] = False
    donor_identifiers_retained: Literal[False] = False
    donor_hashes_retained: Literal[False] = False
    donor_profiles_retained: Literal[False] = False
    feature_identities_retained: Literal[False] = False
    raw_material_retained: Literal[False] = False


class FoldPreparation(_StrictFrozen):
    fold_id: FoldId
    kind: ValidationKind
    state: Literal["prepared", "abstained"]
    abstention_reason: PreparationReason | None
    eligible_lineage_count: int = Field(ge=0, le=20)
    selected_feature_count: int = Field(ge=0, le=512)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        _fold_kind(self.fold_id, self.kind)
        if self.state == "prepared":
            if (
                self.abstention_reason is not None
                or min(self.eligible_lineage_count, self.selected_feature_count) < 2
            ):
                raise ValueError("prepared fold dimensions or reason are inconsistent")
        elif self.abstention_reason is None:
            raise ValueError("abstained fold requires its preparation reason")
        return self


class ValidationTask(_StrictFrozen):
    task_digest: Sha256Digest
    fold_id: FoldId
    kind: ValidationKind
    shrinkage_index: int = Field(ge=0, le=3)
    shrinkage: float = Field(gt=0.0)
    modeled_label: str
    training_record_count: int = Field(ge=1)
    training_study_count: int = Field(ge=1)
    selected_feature_count: int = Field(ge=2, le=512)
    selected_feature_axis_digest: Sha256Digest
    training_matrix_digest: Sha256Digest

    _float = field_validator("shrinkage", mode="before")(_strict_float)

    @model_validator(mode="after")
    def validate_task(self) -> Self:
        _fold_kind(self.fold_id, self.kind)
        if self.modeled_label not in PRODUCTION_SOURCE_LABELS:
            raise ValueError("task label is outside the complete source taxonomy")
        if self.shrinkage != SHRINKAGE_GRID[self.shrinkage_index]:
            raise ValueError("task shrinkage does not match the fixed candidate grid")
        if self.training_study_count > self.training_record_count:
            raise ValueError("task study count exceeds its record count")
        body = self.model_dump(mode="json", exclude={"task_digest"})
        if self.task_digest != sha256_digest(
            {"schema": "gbmap-hierarchy-validation-task/1.0.0", **body}
        ):
            raise ValueError("task canonical digest does not verify")
        return self


class ValidationRunManifest(_Flags):
    schema_version: Literal["glio-proteogen.gbmap-hierarchy-run-manifest/1.0.0"]
    manifest_digest: Sha256Digest
    run_state: Literal["development_validation_hierarchy_tasks_only"]
    reviewed_sha256: Sha256Digest
    source_bytes: int = Field(gt=0)
    taxonomy_digest: Sha256Digest
    extraction_recipe_digest: Sha256Digest
    extraction_receipt_digest: Sha256Digest
    preflight_receipt_digest: Sha256Digest
    preflight_task_dimensions_digest: Sha256Digest
    profile_id: str = Field(pattern=r"^gbmap-dm-composition/[0-9]+\.[0-9]+\.[0-9]+(?:-dev)?$")
    profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    training_configuration_digest: Sha256Digest
    split_receipt_digest: Sha256Digest
    feature_order_digest: Sha256Digest
    preparation_receipts: tuple[FoldPreparation, ...] = Field(min_length=1, max_length=MAX_FOLDS)
    task_inventory_digest: Sha256Digest
    task_count: int = Field(ge=0, le=MAX_TASKS)
    preflight_hierarchy_fit_upper_bound: int = Field(ge=0, le=MAX_TASKS)
    tasks: tuple[ValidationTask, ...] = Field(max_length=MAX_TASKS)

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        if (
            self.task_count != len(self.tasks)
            or self.task_count > self.preflight_hierarchy_fit_upper_bound
        ):
            raise ValueError("task count or preflight bound does not conserve the inventory")
        fold_ids = tuple(row.fold_id for row in self.preparation_receipts)
        coordinates = tuple((x.fold_id, x.shrinkage_index, x.modeled_label) for x in self.tasks)
        if fold_ids != tuple(sorted(set(fold_ids))) or coordinates != tuple(
            sorted(set(coordinates))
        ):
            raise ValueError("fold and task inventories must be uniquely lexical")
        if len({x.task_digest for x in self.tasks}) != len(self.tasks):
            raise ValueError("task digests must be unique")
        grouped: dict[str, list[ValidationTask]] = {key: [] for key in fold_ids}
        for task in self.tasks:
            if task.fold_id not in grouped:
                raise ValueError("task has no declared preparation fold")
            grouped[task.fold_id].append(task)
        for preparation in self.preparation_receipts:
            tasks = grouped[preparation.fold_id]
            if preparation.state == "abstained":
                if tasks:
                    raise ValueError("abstained preparation cannot contain hierarchy tasks")
                continue
            first = tuple(x for x in tasks if x.shrinkage_index == 0)
            if len(first) != preparation.eligible_lineage_count:
                raise ValueError("prepared fold lineage inventory is incomplete")
            basis = {
                x.modeled_label: (
                    x.training_record_count,
                    x.training_study_count,
                    x.selected_feature_count,
                    x.selected_feature_axis_digest,
                    x.training_matrix_digest,
                )
                for x in first
            }
            if len({x.selected_feature_axis_digest for x in first}) != 1:
                raise ValueError("prepared fold tasks use inconsistent feature axes")
            for index in range(len(SHRINKAGE_GRID)):
                current = tuple(x for x in tasks if x.shrinkage_index == index)
                if len(current) != len(first) or {x.modeled_label for x in current} != set(basis):
                    raise ValueError("all four candidates require the same exact fold lineage axis")
                for task in current:
                    if (
                        task.kind != preparation.kind
                        or task.selected_feature_count != preparation.selected_feature_count
                    ):
                        raise ValueError("task disagrees with its preparation family or dimensions")
                    if (
                        task.training_record_count,
                        task.training_study_count,
                        task.selected_feature_count,
                        task.selected_feature_axis_digest,
                        task.training_matrix_digest,
                    ) != basis[task.modeled_label]:
                        raise ValueError("candidate tasks do not share their exact training basis")
        inventory = {
            "schema": "gbmap-hierarchy-task-inventory/1.0.0",
            "tasks": [x.model_dump(mode="json") for x in self.tasks],
        }
        if self.task_inventory_digest != sha256_digest(inventory):
            raise ValueError("task inventory seal does not verify")
        if self.manifest_digest != sha256_digest(
            self.model_dump(mode="json", exclude={"manifest_digest"})
        ):
            raise ValueError("manifest canonical seal does not verify")
        return self


class EvaluationOutput(_StrictFrozen):
    evaluation_output_digest: Sha256Digest
    state: Literal["evaluated", "abstained"]
    abstention_reason: TaskFailureReason | None
    hierarchy_fit_digest: Sha256Digest | None
    hierarchy_trace_digest: Sha256Digest | None
    hierarchy_converged: bool | None
    hierarchy_iterations: int | None = Field(ge=0)
    hierarchy_initial_objective: float | None = Field(ge=0.0)
    hierarchy_objective: float | None = Field(ge=0.0)
    hierarchy_kkt_residual: float | None = Field(ge=0.0)
    evaluated_held_record_count: int = Field(ge=0)
    evaluated_held_study_count: int = Field(ge=0)
    mean_per_count_nll: float | None = Field(ge=0.0)

    _floats = field_validator(
        "hierarchy_initial_objective",
        "hierarchy_objective",
        "hierarchy_kkt_residual",
        "mean_per_count_nll",
        mode="before",
    )(_strict_float)

    @model_validator(mode="after")
    def validate_evaluation(self) -> Self:
        diagnostics = (
            self.hierarchy_fit_digest,
            self.hierarchy_trace_digest,
            self.hierarchy_converged,
            self.hierarchy_iterations,
            self.hierarchy_initial_objective,
            self.hierarchy_objective,
            self.hierarchy_kkt_residual,
        )
        if self.state == "evaluated":
            if (
                self.abstention_reason is not None
                or any(x is None for x in diagnostics)
                or self.hierarchy_converged is not True
                or self.mean_per_count_nll is None
                or min(self.evaluated_held_record_count, self.evaluated_held_study_count) < 1
            ):
                raise ValueError("evaluated checkpoint has incomplete diagnostic or held evidence")
        elif (
            self.abstention_reason is None
            or self.mean_per_count_nll is not None
            or self.evaluated_held_record_count
            or self.evaluated_held_study_count
        ):
            raise ValueError("abstained checkpoint cannot retain a held score")
        if self.abstention_reason == "hierarchy_fit_failed":
            if any(x is not None for x in diagnostics):
                raise ValueError("failed fitting cannot retain hierarchy diagnostics")
        elif self.state == "abstained" and any(x is None for x in diagnostics):
            raise ValueError("post-fit abstention requires its hierarchy diagnostics")
        if self.evaluated_held_study_count > self.evaluated_held_record_count:
            raise ValueError("held study count exceeds held record count")
        body = self.model_dump(mode="json", exclude={"evaluation_output_digest"})
        if self.evaluation_output_digest != sha256_digest(
            {"schema": "gbmap-hierarchy-evaluation-output/1.0.0", **body}
        ):
            raise ValueError("evaluation canonical seal does not verify")
        return self


class ValidationCheckpoint(_Flags):
    schema_version: Literal["glio-proteogen.gbmap-hierarchy-checkpoint/1.0.0"]
    checkpoint_digest: Sha256Digest
    manifest_digest: Sha256Digest
    task_digest: Sha256Digest
    fold_id: FoldId
    kind: ValidationKind
    shrinkage_index: int = Field(ge=0, le=3)
    shrinkage: float = Field(gt=0.0)
    modeled_label: str
    reviewed_sha256: Sha256Digest
    profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    training_configuration_digest: Sha256Digest
    split_receipt_digest: Sha256Digest
    feature_order_digest: Sha256Digest
    selected_feature_axis_digest: Sha256Digest
    training_matrix_digest: Sha256Digest
    evaluation: EvaluationOutput

    _float = field_validator("shrinkage", mode="before")(_strict_float)

    @model_validator(mode="after")
    def validate_checkpoint(self) -> Self:
        _fold_kind(self.fold_id, self.kind)
        if (
            self.modeled_label not in PRODUCTION_SOURCE_LABELS
            or self.shrinkage != SHRINKAGE_GRID[self.shrinkage_index]
        ):
            raise ValueError("checkpoint coordinate is outside the fixed candidate taxonomy")
        if self.checkpoint_digest != sha256_digest(
            self.model_dump(mode="json", exclude={"checkpoint_digest"})
        ):
            raise ValueError("checkpoint canonical seal does not verify")
        return self


class PlanningFeasibilityReceipt(_StrictFrozen):
    profile_id: Literal["gbmap-complete-development-reduction/1.0.0"] = REDUCTION_PROFILE_ID
    manifest_digest: Sha256Digest
    task_inventory_digest: Sha256Digest
    prepared_whole_study_folds: int = Field(ge=0, le=MAX_FOLDS)
    prepared_within_study_donor_folds: int = Field(ge=0, le=MAX_FOLDS)
    minimum_whole_study_folds: Literal[3] = 3
    minimum_within_study_donor_folds: Literal[5] = 5
    whole_study_shortfall: int = Field(ge=0, le=3)
    within_study_donor_shortfall: int = Field(ge=0, le=5)
    planning_gate_status: Literal["potentially_feasible", "infeasible_preparation_support"]
    numerical_or_marker_success_established: Literal[False] = False
    model_selection_performed: Literal[False] = False
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.prepared_whole_study_folds + self.prepared_within_study_donor_folds > MAX_FOLDS:
            raise ValueError("planning fold inventory exceeds its complete bound")
        deficits = (
            max(0, 3 - self.prepared_whole_study_folds),
            max(0, 5 - self.prepared_within_study_donor_folds),
        )
        if (
            self.whole_study_shortfall,
            self.within_study_donor_shortfall,
        ) != deficits or self.planning_gate_status != (
            "infeasible_preparation_support" if any(deficits) else "potentially_feasible"
        ):
            raise ValueError("planning support does not conserve fixed validation gates")
        if self.receipt_digest != sha256_digest(
            self.model_dump(mode="json", exclude={"receipt_digest"})
        ):
            raise ValueError("planning receipt seal does not verify")
        return self


class ReducedFold(_StrictFrozen):
    fold_id: FoldId
    kind: ValidationKind
    state: Literal["evaluated", "abstained"]
    abstention_reason: FoldReason | None
    eligible_lineage_count: int = Field(ge=0, le=20)
    selected_feature_count: int = Field(ge=0, le=512)
    task_count: int = Field(ge=0, le=20)
    evaluated_task_count: int = Field(ge=0, le=20)
    evaluated_held_record_count: int = Field(ge=0)
    mean_per_count_nll: float | None = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        _fold_kind(self.fold_id, self.kind)
        if self.evaluated_task_count > self.task_count:
            raise ValueError("evaluated task count exceeds its complete fold inventory")
        if self.state == "evaluated":
            if (
                self.abstention_reason is not None
                or self.task_count != self.eligible_lineage_count
                or self.task_count < 2
                or self.selected_feature_count < 2
                or self.evaluated_task_count != self.task_count
                or self.evaluated_held_record_count < self.task_count
                or self.mean_per_count_nll is None
            ):
                raise ValueError("accepted fold requires every lineage and finite held evidence")
        elif (
            self.abstention_reason is None
            or self.mean_per_count_nll is not None
            or self.evaluated_held_record_count
        ):
            raise ValueError("abstained fold cannot retain a partial aggregate score")
        if self.state == "abstained":
            preparation_reasons = {
                "split_not_evaluable",
                "stable_gene_selection_failed",
                "fewer_than_two_eligible_lineages",
                "selected_marker_union_too_small",
            }
            if self.abstention_reason in preparation_reasons:
                if self.task_count or self.evaluated_task_count:
                    raise ValueError("preparation abstention cannot contain fitted tasks")
            elif (
                self.task_count != self.eligible_lineage_count
                or self.task_count < 2
                or self.evaluated_task_count == self.task_count
            ):
                raise ValueError(
                    "numerical abstention requires a complete fold with at least one failed task"
                )
        return self


class LineageValidationCoverage(_StrictFrozen):
    modeled_label: str
    whole_study_fold_count: int = Field(ge=0, le=MAX_FOLDS)
    within_study_donor_fold_count: int = Field(ge=0, le=MAX_FOLDS)
    minimum_whole_study_folds: Literal[3] = 3
    minimum_within_study_donor_folds: Literal[5] = 5
    validation_coverage_eligible: bool
    abstention_reasons: tuple[
        Literal[
            "no_selected_candidate",
            "insufficient_whole_study_validation_folds",
            "insufficient_within_study_donor_validation_folds",
        ],
        ...,
    ]
    policy_id: Literal["gbmap-final-lineage-validation-coverage/1.0.0"] = LINEAGE_POLICY_ID
    full_source_support_rechecked: Literal[False] = False
    final_fit_eligibility_established: Literal[False] = False

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.modeled_label not in PRODUCTION_SOURCE_LABELS:
            raise ValueError("lineage ledger must use the complete source taxonomy")
        expected = tuple(
            reason
            for count, minimum, reason in (
                (self.whole_study_fold_count, 3, "insufficient_whole_study_validation_folds"),
                (
                    self.within_study_donor_fold_count,
                    5,
                    "insufficient_within_study_donor_validation_folds",
                ),
            )
            if count < minimum
        )
        if self.abstention_reasons and self.abstention_reasons[0] == "no_selected_candidate":
            expected = ("no_selected_candidate", *expected)
            if self.whole_study_fold_count or self.within_study_donor_fold_count:
                raise ValueError(
                    "unselected lineage ledger cannot carry selected-candidate coverage"
                )
        if self.abstention_reasons != expected or self.validation_coverage_eligible is not (
            not expected
        ):
            raise ValueError("lineage coverage does not conserve the new explicit 3/5 policy")
        return self


class ReducedCandidate(_StrictFrozen):
    shrinkage_index: int = Field(ge=0, le=3)
    shrinkage: float = Field(gt=0.0)
    folds: tuple[ReducedFold, ...] = Field(min_length=1, max_length=MAX_FOLDS)
    whole_study_fold_count: int = Field(ge=0, le=MAX_FOLDS)
    within_study_donor_fold_count: int = Field(ge=0, le=MAX_FOLDS)
    whole_study_mean_nll: float | None = Field(ge=0.0)
    within_study_donor_mean_nll: float | None = Field(ge=0.0)
    selection_score: float | None = Field(ge=0.0)
    selectable: bool
    lineage_coverage: tuple[LineageValidationCoverage, ...] = Field(min_length=20, max_length=20)

    @model_validator(mode="after")
    def validate_arithmetic(self) -> Self:
        if self.shrinkage != SHRINKAGE_GRID[self.shrinkage_index]:
            raise ValueError("candidate index and shrinkage disagree")
        ids = tuple(x.fold_id for x in self.folds)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("candidate fold axis must be uniquely lexical")
        whole = tuple(
            x.mean_per_count_nll
            for x in self.folds
            if x.state == "evaluated" and x.kind == "whole_study"
        )
        within = tuple(
            x.mean_per_count_nll
            for x in self.folds
            if x.state == "evaluated" and x.kind == "within_study_donor"
        )
        means = tuple(
            None if not values else math.fsum(x for x in values if x is not None) / len(values)
            for values in (whole, within)
        )
        if (self.whole_study_fold_count, self.within_study_donor_fold_count) != (
            len(whole),
            len(within),
        ) or (self.whole_study_mean_nll, self.within_study_donor_mean_nll) != means:
            raise ValueError("candidate validation family means do not conserve complete folds")
        score = None
        if len(whole) >= 3 and len(within) >= 5 and means[0] is not None and means[1] is not None:
            score = math.fsum((means[0], means[1])) / 2.0
        if self.selection_score != score or self.selectable is not (score is not None):
            raise ValueError("candidate selection does not conserve the unchanged 3/5 gates")
        if tuple(x.modeled_label for x in self.lineage_coverage) != PRODUCTION_SOURCE_LABELS:
            raise ValueError("candidate must preserve every source label in exact taxonomy order")
        if any(
            row.whole_study_fold_count > self.whole_study_fold_count
            or row.within_study_donor_fold_count > self.within_study_donor_fold_count
            or "no_selected_candidate" in row.abstention_reasons
            for row in self.lineage_coverage
        ):
            raise ValueError("candidate lineage coverage exceeds its whole accepted-fold evidence")
        return self


class CandidateSelectionReceipt(_Flags):
    schema_version: Literal["gbmap-complete-candidate-selection/1.0.0"] = (
        "gbmap-complete-candidate-selection/1.0.0"
    )
    profile_id: Literal["gbmap-complete-development-reduction/1.0.0"] = REDUCTION_PROFILE_ID
    manifest_digest: Sha256Digest
    task_inventory_digest: Sha256Digest
    checkpoint_set_digest: Sha256Digest
    completed_checkpoint_count: int = Field(ge=0, le=MAX_TASKS)
    inherited_profile_id: str
    inherited_profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    training_configuration_digest: Sha256Digest
    reviewed_sha256: Sha256Digest
    source_bytes: int = Field(gt=0)
    split_receipt_digest: Sha256Digest
    feature_order_digest: Sha256Digest
    planning: PlanningFeasibilityReceipt
    candidates: tuple[ReducedCandidate, ...] = Field(min_length=4, max_length=4)
    selected_shrinkage_index: int | None = Field(ge=0, le=3)
    selected_shrinkage: float | None = Field(gt=0.0)
    selection_abstention_reason: Literal["no_candidate_passes_validation_family_gates"] | None
    lineage_coverage: tuple[LineageValidationCoverage, ...] = Field(min_length=20, max_length=20)
    selection_score_is_unbiased_performance_estimate: Literal[False] = False
    mixture_accuracy_established: Literal[False] = False
    external_validation_established: Literal[False] = False
    private_training_matrix_reconstruction_performed: Literal[False] = False
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        if self.completed_checkpoint_count != sum(
            fold.task_count for candidate in self.candidates for fold in candidate.folds
        ):
            raise ValueError("completed checkpoint count does not conserve all candidate tasks")
        if tuple(x.shrinkage for x in self.candidates) != SHRINKAGE_GRID or tuple(
            x.shrinkage_index for x in self.candidates
        ) != (0, 1, 2, 3):
            raise ValueError("selection must retain all four fixed candidates")
        fold_axes = {tuple((f.fold_id, f.kind) for f in x.folds) for x in self.candidates}
        if (
            len(fold_axes) != 1
            or self.planning.manifest_digest != self.manifest_digest
            or self.planning.task_inventory_digest != self.task_inventory_digest
        ):
            raise ValueError("selection fold axes or planning bindings disagree")
        for candidate in self.candidates:
            counts = tuple(
                sum(f.task_count > 0 and f.kind == kind for f in candidate.folds)
                for kind in ("whole_study", "within_study_donor")
            )
            if counts != (
                self.planning.prepared_whole_study_folds,
                self.planning.prepared_within_study_donor_folds,
            ):
                raise ValueError(
                    "planning counts do not match complete candidate preparation evidence"
                )
        selectable = tuple(x for x in self.candidates if x.selectable)
        if selectable:
            winner = min(
                selectable,
                key=lambda x: (
                    math.inf if x.selection_score is None else x.selection_score,
                    x.shrinkage,
                ),
            )
            if (
                (self.selected_shrinkage_index, self.selected_shrinkage)
                != (winner.shrinkage_index, winner.shrinkage)
                or self.selection_abstention_reason is not None
                or self.lineage_coverage != winner.lineage_coverage
            ):
                raise ValueError(
                    "selected candidate must minimize score with smallest-shrinkage exact ties"
                )
        elif (
            self.selected_shrinkage_index is not None
            or self.selected_shrinkage is not None
            or self.selection_abstention_reason != "no_candidate_passes_validation_family_gates"
        ):
            raise ValueError("no selectable candidate must remain an explicit unselected result")
        if tuple(x.modeled_label for x in self.lineage_coverage) != PRODUCTION_SOURCE_LABELS:
            raise ValueError("selection must retain the complete source label ledger")
        if not selectable and any(
            x.abstention_reasons[:1] != ("no_selected_candidate",) for x in self.lineage_coverage
        ):
            raise ValueError("unselected candidate ledger must retain explicit nonselection")
        if self.receipt_digest != sha256_digest(
            self.model_dump(mode="json", exclude={"receipt_digest"})
        ):
            raise ValueError("selection receipt canonical seal does not verify")
        return self

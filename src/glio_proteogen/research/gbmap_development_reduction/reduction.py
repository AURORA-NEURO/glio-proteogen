"""Pure complete-task reduction; no fitting, source I/O or publication."""

from __future__ import annotations

import math
from collections import defaultdict

from pydantic import ValidationError

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS

from .contracts import (
    SHRINKAGE_GRID,
    CandidateSelectionReceipt,
    FoldPreparation,
    FoldReason,
    LineageValidationCoverage,
    PlanningFeasibilityReceipt,
    ReducedCandidate,
    ReducedFold,
    ReductionError,
    ValidationCheckpoint,
    ValidationRunManifest,
)


def _manifest(value: ValidationRunManifest) -> ValidationRunManifest:
    if type(value) is not ValidationRunManifest:
        raise ReductionError("an exact closed validation-run manifest is required")
    try:
        return ValidationRunManifest.model_validate(value.model_dump(mode="python"))
    except (ValidationError, ValueError, TypeError):
        raise ReductionError("validation manifest failed strict canonical revalidation") from None


def assess_manifest_feasibility(manifest: ValidationRunManifest) -> PlanningFeasibilityReceipt:
    """Detect necessary preparation-support shortfalls before expensive fits."""
    checked = _manifest(manifest)
    whole = sum(
        x.state == "prepared" and x.kind == "whole_study" for x in checked.preparation_receipts
    )
    within = sum(
        x.state == "prepared" and x.kind == "within_study_donor"
        for x in checked.preparation_receipts
    )
    deficits = (max(0, 3 - whole), max(0, 5 - within))
    body = {
        "profile_id": "gbmap-complete-development-reduction/1.0.0",
        "manifest_digest": checked.manifest_digest,
        "task_inventory_digest": checked.task_inventory_digest,
        "prepared_whole_study_folds": whole,
        "prepared_within_study_donor_folds": within,
        "minimum_whole_study_folds": 3,
        "minimum_within_study_donor_folds": 5,
        "whole_study_shortfall": deficits[0],
        "within_study_donor_shortfall": deficits[1],
        "planning_gate_status": "infeasible_preparation_support"
        if any(deficits)
        else "potentially_feasible",
        "numerical_or_marker_success_established": False,
        "model_selection_performed": False,
    }
    return PlanningFeasibilityReceipt.model_validate(
        {**body, "receipt_digest": sha256_digest(body)}
    )


def _fold(preparation: FoldPreparation, rows: tuple[ValidationCheckpoint, ...]) -> ReducedFold:
    accepted = tuple(x for x in rows if x.evaluation.state == "evaluated")
    reason: FoldReason | None = preparation.abstention_reason
    if preparation.state == "prepared" and len(accepted) != len(rows):
        failures = {x.evaluation.abstention_reason for x in rows}
        if "hierarchy_fit_failed" in failures:
            reason = "hierarchy_fit_failed"
        elif failures & {"hierarchy_did_not_converge", "hierarchy_trace_invalid"}:
            reason = "hierarchy_did_not_converge"
        else:
            reason = "no_positive_held_marker_counts"
    score = None
    held = 0
    if reason is None:
        scores = tuple(x.evaluation.mean_per_count_nll for x in accepted)
        score = math.fsum(x for x in scores if x is not None) / len(scores)
        held = sum(x.evaluation.evaluated_held_record_count for x in accepted)
    return ReducedFold(
        fold_id=preparation.fold_id,
        kind=preparation.kind,
        state="evaluated" if reason is None else "abstained",
        abstention_reason=reason,
        eligible_lineage_count=preparation.eligible_lineage_count,
        selected_feature_count=preparation.selected_feature_count,
        task_count=len(rows),
        evaluated_task_count=len(accepted),
        evaluated_held_record_count=held,
        mean_per_count_nll=score,
    )


def _coverage(
    label: str, whole: int, within: int, *, unselected: bool = False
) -> LineageValidationCoverage:
    reasons = []
    if unselected:
        reasons.append("no_selected_candidate")
    if whole < 3:
        reasons.append("insufficient_whole_study_validation_folds")
    if within < 5:
        reasons.append("insufficient_within_study_donor_validation_folds")
    return LineageValidationCoverage.model_validate(
        {
            "modeled_label": label,
            "whole_study_fold_count": whole,
            "within_study_donor_fold_count": within,
            "validation_coverage_eligible": not reasons,
            "abstention_reasons": tuple(reasons),
        }
    )


def reduce_completed_validation(
    manifest: ValidationRunManifest,
    checkpoints: tuple[ValidationCheckpoint, ...],
) -> CandidateSelectionReceipt:
    """Select only from every exact completed task; retain honest nonselection.

    The caller must separately replay source extraction and training-matrix
    bindings with the existing task loader. Sealed aggregate input alone cannot
    establish that those private numerical matrices were reconstructed.
    """
    checked = _manifest(manifest)
    if (
        type(checkpoints) is not tuple
        or len(checkpoints) != checked.task_count
        or any(type(x) is not ValidationCheckpoint for x in checkpoints)
    ):
        raise ReductionError("every exact manifest task requires one closed checkpoint")
    try:
        rows = tuple(
            ValidationCheckpoint.model_validate(x.model_dump(mode="python")) for x in checkpoints
        )
    except (ValidationError, ValueError, TypeError):
        raise ReductionError("checkpoint failed strict canonical revalidation") from None
    by_task = {x.task_digest: x for x in rows}
    if len(by_task) != len(rows) or set(by_task) != {x.task_digest for x in checked.tasks}:
        raise ReductionError("duplicate, extra or missing task checkpoints are forbidden")
    inherited = (
        "reviewed_sha256",
        "profile_digest",
        "engine_semantic_digest",
        "training_configuration_digest",
        "split_receipt_digest",
        "feature_order_digest",
    )
    coordinate = (
        "fold_id",
        "kind",
        "shrinkage_index",
        "shrinkage",
        "modeled_label",
        "selected_feature_axis_digest",
        "training_matrix_digest",
    )
    grouped: dict[tuple[str, int], list[ValidationCheckpoint]] = defaultdict(list)
    ordered = tuple(by_task[task.task_digest] for task in checked.tasks)
    for task, row in zip(checked.tasks, ordered, strict=True):
        if (
            row.manifest_digest != checked.manifest_digest
            or any(getattr(row, name) != getattr(checked, name) for name in inherited)
            or any(getattr(row, name) != getattr(task, name) for name in coordinate)
        ):
            raise ReductionError(
                "checkpoint provenance, feature axis or training basis differs from its exact task"
            )
        grouped[(task.fold_id, task.shrinkage_index)].append(row)
    candidates = []
    for index, shrinkage in enumerate(SHRINKAGE_GRID):
        folds = tuple(
            _fold(prep, tuple(grouped[(prep.fold_id, index)]))
            for prep in checked.preparation_receipts
        )
        means = []
        counts = []
        for kind in ("whole_study", "within_study_donor"):
            scores = tuple(
                x.mean_per_count_nll for x in folds if x.state == "evaluated" and x.kind == kind
            )
            counts.append(len(scores))
            means.append(
                None if not scores else math.fsum(x for x in scores if x is not None) / len(scores)
            )
        score = None
        if counts[0] >= 3 and counts[1] >= 5 and means[0] is not None and means[1] is not None:
            score = math.fsum((means[0], means[1])) / 2.0
        coverage = []
        for label in PRODUCTION_SOURCE_LABELS:
            label_counts = [
                sum(
                    f.state == "evaluated"
                    and f.kind == kind
                    and any(x.modeled_label == label for x in grouped[(f.fold_id, index)])
                    for f in folds
                )
                for kind in ("whole_study", "within_study_donor")
            ]
            coverage.append(_coverage(label, label_counts[0], label_counts[1]))
        candidates.append(
            ReducedCandidate(
                shrinkage_index=index,
                shrinkage=shrinkage,
                folds=folds,
                whole_study_fold_count=counts[0],
                within_study_donor_fold_count=counts[1],
                whole_study_mean_nll=means[0],
                within_study_donor_mean_nll=means[1],
                selection_score=score,
                selectable=score is not None,
                lineage_coverage=tuple(coverage),
            )
        )
    selectable = tuple(x for x in candidates if x.selectable)
    selected = (
        min(
            selectable,
            key=lambda x: (
                math.inf if x.selection_score is None else x.selection_score,
                x.shrinkage,
            ),
        )
        if selectable
        else None
    )
    body = {
        "schema_version": "gbmap-complete-candidate-selection/1.0.0",
        "profile_id": "gbmap-complete-development-reduction/1.0.0",
        "manifest_digest": checked.manifest_digest,
        "task_inventory_digest": checked.task_inventory_digest,
        "checkpoint_set_digest": sha256_digest(
            {
                "schema": "gbmap-complete-checkpoint-set/1.0.0",
                "checkpoint_digests": [x.checkpoint_digest for x in ordered],
            }
        ),
        "completed_checkpoint_count": len(ordered),
        "inherited_profile_id": checked.profile_id,
        "inherited_profile_digest": checked.profile_digest,
        "engine_semantic_digest": checked.engine_semantic_digest,
        "training_configuration_digest": checked.training_configuration_digest,
        "reviewed_sha256": checked.reviewed_sha256,
        "source_bytes": checked.source_bytes,
        "split_receipt_digest": checked.split_receipt_digest,
        "feature_order_digest": checked.feature_order_digest,
        "planning": assess_manifest_feasibility(checked).model_dump(mode="json"),
        "candidates": tuple(x.model_dump(mode="python") for x in candidates),
        "selected_shrinkage_index": None if selected is None else selected.shrinkage_index,
        "selected_shrinkage": None if selected is None else selected.shrinkage,
        "selection_abstention_reason": "no_candidate_passes_validation_family_gates"
        if selected is None
        else None,
        "lineage_coverage": tuple(
            x.model_dump(mode="python")
            for x in (
                tuple(_coverage(label, 0, 0, unselected=True) for label in PRODUCTION_SOURCE_LABELS)
                if selected is None
                else selected.lineage_coverage
            )
        ),
        "selection_score_is_unbiased_performance_estimate": False,
        "mixture_accuracy_established": False,
        "external_validation_established": False,
        "private_training_matrix_reconstruction_performed": False,
    }
    body.update(
        {
            name: False
            for name in ValidationRunManifest.model_fields
            if name
            in {
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
            }
        }
    )
    return CandidateSelectionReceipt.model_validate({**body, "receipt_digest": sha256_digest(body)})

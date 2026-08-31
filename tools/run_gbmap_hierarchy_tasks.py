"""Execute private GBmap validation hierarchies as deterministic resumable tasks.

The command re-extracts the exact reviewed H5AD on every invocation, reconciles
an immutable structural-preflight receipt, rebuilds fold-local marker matrices,
and executes only a bounded lexical prefix of pending hierarchy tasks.  Durable
state is limited to a deidentified run manifest and content-addressed numerical
checkpoints.  Nothing produced here is an admitted model, artifact, runtime, API,
or public CLI surface.
"""

# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
import stat
import sys
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Protocol, Self, cast

import numpy as np
from pydantic import Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.gbmap_deconvolution import (
    DEFAULT_TRAINING_CONFIGURATION,
    GbmapDeconvolutionError,
    GbmapExtractionResult,
    GbmapInputError,
    GbmapNumericalError,
    LineageHierarchyFit,
    TrainingConfiguration,
    ValidationKind,
    ValidationSplitPlan,
    build_validation_split_plan,
    development_profile,
    dirichlet_multinomial_per_count_nll,
    extract_pinned_gbmap_reference,
    production_donor_crosswalk,
    production_extraction_recipe,
    production_label_taxonomy,
    production_study_crosswalk,
    verify_hierarchy_trace,
)
from glio_proteogen.research.gbmap_deconvolution.training import (
    _AbstainedFold,
    _fit_label,
    _prepare_fold,
    _PreparedFold,
)
from tools import fit_gbmap_development_candidate as fit_driver
from tools import preflight_gbmap_development_candidate as preflight_driver
from tools.capture_gbmap_source_admission import write_receipt

MANIFEST_SCHEMA: Final = "glio-proteogen.gbmap-hierarchy-run-manifest/1.0.0"
CHECKPOINT_SCHEMA: Final = "glio-proteogen.gbmap-hierarchy-checkpoint/1.0.0"
BATCH_RECEIPT_SCHEMA: Final = "glio-proteogen.gbmap-hierarchy-batch-receipt/1.0.0"
TASK_SCHEMA: Final = "gbmap-hierarchy-validation-task/1.0.0"
TASK_INVENTORY_SCHEMA: Final = "gbmap-hierarchy-task-inventory/1.0.0"
TRAINING_MATRIX_SCHEMA: Final = "gbmap-hierarchy-training-matrix/1.0.0"
FEATURE_AXIS_SCHEMA: Final = "gbmap-selected-feature-axis/1.0.0"
EVALUATION_OUTPUT_SCHEMA: Final = "gbmap-hierarchy-evaluation-output/1.0.0"
HIERARCHY_FIT_DIGEST_SCHEMA: Final = "gbmap-hierarchy-transient-fit/1.0.0"

MANIFEST_NAME: Final = "run-manifest.json"
CHECKPOINT_DIRECTORY_NAME: Final = "checkpoints"
MAX_MANIFEST_BYTES: Final = 16 * 1024 * 1024
MAX_CHECKPOINT_BYTES: Final = 4 * 1024 * 1024
MAX_PREFLIGHT_BYTES: Final = preflight_driver.MAX_OUTPUT_BYTES
MAX_TASKS_PER_BATCH: Final = 256
_MINIMUM_MODELED_DIMENSION: Final = 2

_SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_CHECKPOINT_NAME_PATTERN: Final = re.compile(r"^[0-9a-f]{64}\.[0-9a-f]{64}\.json$")

TaskState = Literal["evaluated", "abstained"]
TaskFailureReason = Literal[
    "hierarchy_did_not_converge",
    "hierarchy_fit_failed",
    "hierarchy_trace_invalid",
    "no_positive_held_marker_counts",
]
PreparationState = Literal["prepared", "abstained"]


class _DigestWriter(Protocol):
    def update(self, value: bytes, /) -> None: ...


class GbmapHierarchyTaskDriverError(RuntimeError):
    """Private staged execution failed without retaining sensitive context."""


def _privacy_call[T](message: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except Exception:  # noqa: BLE001 - sanitize all path/data-bearing internals
        raise GbmapHierarchyTaskDriverError(message) from None


class GbmapFoldPreparationReceipt(FrozenModel):
    """Non-identifying result of exact fold-local marker preparation."""

    fold_id: str = Field(pattern=r"^(?:whole-study|within-study-donor)-[0-9]{4}$")
    kind: ValidationKind
    state: PreparationState
    abstention_reason: str | None
    eligible_lineage_count: int = Field(ge=0)
    selected_feature_count: int = Field(ge=0)

    @model_validator(mode="after")
    def state_is_consistent(self) -> Self:
        if self.state == "prepared":
            if (
                self.abstention_reason is not None
                or self.eligible_lineage_count < _MINIMUM_MODELED_DIMENSION
                or self.selected_feature_count < _MINIMUM_MODELED_DIMENSION
            ):
                raise ValueError("prepared fold receipt is inconsistent")
        elif self.abstention_reason is None:
            raise ValueError("abstained fold receipt requires a reason")
        return self


class GbmapHierarchyTaskSpec(FrozenModel):
    """One content-bound fold, shrinkage, and modeled-lineage task."""

    task_digest: Sha256Digest
    fold_id: str = Field(pattern=r"^(?:whole-study|within-study-donor)-[0-9]{4}$")
    kind: ValidationKind
    shrinkage_index: int = Field(ge=0)
    shrinkage: float = Field(gt=0.0)
    modeled_label: str = Field(min_length=1, max_length=256)
    training_record_count: int = Field(gt=0)
    training_study_count: int = Field(gt=0)
    selected_feature_count: int = Field(ge=2)
    selected_feature_axis_digest: Sha256Digest
    training_matrix_digest: Sha256Digest

    @model_validator(mode="after")
    def task_digest_verifies(self) -> Self:
        body = self.model_dump(mode="json", exclude={"task_digest"})
        if self.task_digest != sha256_digest({"schema": TASK_SCHEMA, **body}):
            raise ValueError("GBmap hierarchy task digest mismatch")
        return self


class GbmapHierarchyRunManifest(FrozenModel):
    """Immutable deidentified inventory for one exact validation-task run."""

    schema_version: Literal["glio-proteogen.gbmap-hierarchy-run-manifest/1.0.0"] = MANIFEST_SCHEMA
    manifest_digest: Sha256Digest
    run_state: Literal["development_validation_hierarchy_tasks_only"] = (
        "development_validation_hierarchy_tasks_only"
    )
    reviewed_sha256: Sha256Digest
    source_bytes: int = Field(gt=0)
    taxonomy_digest: Sha256Digest
    extraction_recipe_digest: Sha256Digest
    extraction_receipt_digest: Sha256Digest
    preflight_receipt_digest: Sha256Digest
    preflight_task_dimensions_digest: Sha256Digest
    profile_id: Literal["gbmap-dm-composition/0.1.0-dev"]
    profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    training_configuration_digest: Sha256Digest
    split_receipt_digest: Sha256Digest
    feature_order_digest: Sha256Digest
    preparation_receipts: tuple[GbmapFoldPreparationReceipt, ...]
    task_inventory_digest: Sha256Digest
    task_count: int = Field(ge=0)
    preflight_hierarchy_fit_upper_bound: int = Field(ge=0)
    tasks: tuple[GbmapHierarchyTaskSpec, ...]
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

    @model_validator(mode="after")
    def manifest_is_consistent(self) -> Self:
        if self.task_count != len(self.tasks):
            raise ValueError("GBmap hierarchy task count does not reconcile")
        if self.task_count > self.preflight_hierarchy_fit_upper_bound:
            raise ValueError("GBmap hierarchy tasks exceed the preflight upper bound")
        ordering = tuple(
            (task.fold_id, task.shrinkage_index, task.modeled_label) for task in self.tasks
        )
        if ordering != tuple(sorted(ordering)) or len(ordering) != len(set(ordering)):
            raise ValueError("GBmap hierarchy tasks are not uniquely lexical")
        fold_order = tuple(item.fold_id for item in self.preparation_receipts)
        if fold_order != tuple(sorted(fold_order)) or len(fold_order) != len(set(fold_order)):
            raise ValueError("GBmap fold preparation inventory is not uniquely lexical")
        inventory = sha256_digest(
            {
                "schema": TASK_INVENTORY_SCHEMA,
                "tasks": [task.model_dump(mode="json") for task in self.tasks],
            }
        )
        if self.task_inventory_digest != inventory:
            raise ValueError("GBmap hierarchy task inventory digest mismatch")
        body = self.model_dump(mode="json", exclude={"manifest_digest"})
        if self.manifest_digest != sha256_digest(body):
            raise ValueError("GBmap hierarchy run manifest digest mismatch")
        return self


class GbmapHierarchyEvaluationOutput(FrozenModel):
    """Deidentified held-evidence result; reusable signatures are never retained."""

    evaluation_output_digest: Sha256Digest
    state: TaskState
    abstention_reason: TaskFailureReason | None
    hierarchy_fit_digest: Sha256Digest | None
    hierarchy_trace_digest: Sha256Digest | None
    hierarchy_converged: bool | None
    hierarchy_iterations: int | None = Field(default=None, ge=0)
    hierarchy_initial_objective: float | None = Field(default=None, ge=0.0)
    hierarchy_objective: float | None = Field(default=None, ge=0.0)
    hierarchy_kkt_residual: float | None = Field(default=None, ge=0.0)
    evaluated_held_record_count: int = Field(ge=0)
    evaluated_held_study_count: int = Field(ge=0)
    mean_per_count_nll: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def evaluation_is_consistent(self) -> Self:
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
                or any(value is None for value in diagnostics)
                or self.hierarchy_converged is not True
                or self.evaluated_held_record_count < 1
                or self.evaluated_held_study_count < 1
                or self.mean_per_count_nll is None
            ):
                raise ValueError("evaluated hierarchy output is inconsistent")
        elif self.abstention_reason is None or self.mean_per_count_nll is not None:
            raise ValueError("abstained hierarchy output is inconsistent")
        if self.abstention_reason == "hierarchy_fit_failed":
            if any(value is not None for value in diagnostics):
                raise ValueError("failed hierarchy output cannot retain fit diagnostics")
        elif self.state == "abstained" and any(value is None for value in diagnostics):
            raise ValueError("post-fit abstention requires hierarchy diagnostics")
        if self.state == "abstained" and (
            self.evaluated_held_record_count != 0 or self.evaluated_held_study_count != 0
        ):
            raise ValueError("abstained hierarchy output cannot retain held scores")
        body = self.model_dump(mode="json", exclude={"evaluation_output_digest"})
        if self.evaluation_output_digest != sha256_digest(
            {"schema": EVALUATION_OUTPUT_SCHEMA, **body}
        ):
            raise ValueError("hierarchy evaluation-output digest mismatch")
        return self


class GbmapHierarchyCheckpoint(FrozenModel):
    """One immutable, content-addressed hierarchy-task result."""

    schema_version: Literal["glio-proteogen.gbmap-hierarchy-checkpoint/1.0.0"] = CHECKPOINT_SCHEMA
    checkpoint_digest: Sha256Digest
    manifest_digest: Sha256Digest
    task_digest: Sha256Digest
    fold_id: str = Field(pattern=r"^(?:whole-study|within-study-donor)-[0-9]{4}$")
    kind: ValidationKind
    shrinkage_index: int = Field(ge=0)
    shrinkage: float = Field(gt=0.0)
    modeled_label: str = Field(min_length=1, max_length=256)
    reviewed_sha256: Sha256Digest
    profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    training_configuration_digest: Sha256Digest
    split_receipt_digest: Sha256Digest
    feature_order_digest: Sha256Digest
    selected_feature_axis_digest: Sha256Digest
    training_matrix_digest: Sha256Digest
    evaluation: GbmapHierarchyEvaluationOutput
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

    @model_validator(mode="after")
    def checkpoint_is_consistent(self) -> Self:
        body = self.model_dump(mode="json", exclude={"checkpoint_digest"})
        if self.checkpoint_digest != sha256_digest(body):
            raise ValueError("GBmap hierarchy checkpoint digest mismatch")
        return self


class GbmapHierarchyBatchReceipt(FrozenModel):
    """Deidentified stdout receipt for one bounded resume invocation."""

    schema_version: Literal["glio-proteogen.gbmap-hierarchy-batch-receipt/1.0.0"] = (
        BATCH_RECEIPT_SCHEMA
    )
    receipt_digest: Sha256Digest
    manifest_digest: Sha256Digest
    task_count: int = Field(ge=0)
    verified_checkpoint_count_before: int = Field(ge=0)
    executed_task_count: int = Field(ge=0)
    verified_checkpoint_count_after: int = Field(ge=0)
    remaining_task_count: int = Field(ge=0)
    max_tasks: int = Field(ge=1, le=MAX_TASKS_PER_BATCH)
    dry_run: bool
    run_complete: bool
    checkpoint_digests: tuple[Sha256Digest, ...]
    source_admission_granted: Literal[False] = False
    final_model_fitted: Literal[False] = False
    model_artifact_emitted: Literal[False] = False
    production_artifact_permitted: Literal[False] = False
    runtime_mount_permitted: Literal[False] = False
    public_http_mounted: Literal[False] = False
    public_cli_mounted: Literal[False] = False

    @model_validator(mode="after")
    def progress_is_consistent(self) -> Self:
        if self.verified_checkpoint_count_after != (
            self.verified_checkpoint_count_before + self.executed_task_count
        ):
            raise ValueError("GBmap batch checkpoint progress does not reconcile")
        if self.verified_checkpoint_count_after + self.remaining_task_count != self.task_count:
            raise ValueError("GBmap batch remaining task count does not reconcile")
        if len(self.checkpoint_digests) != self.executed_task_count:
            raise ValueError("GBmap batch checkpoint digest count does not reconcile")
        if self.dry_run and self.executed_task_count != 0:
            raise ValueError("GBmap dry-run receipt cannot report executed tasks")
        if self.run_complete is not (self.remaining_task_count == 0):
            raise ValueError("GBmap batch completion state does not reconcile")
        body = self.model_dump(mode="json", exclude={"receipt_digest"})
        if self.receipt_digest != sha256_digest(body):
            raise ValueError("GBmap hierarchy batch receipt digest mismatch")
        return self


@dataclass(frozen=True, slots=True)
class _RuntimeTask:
    spec: GbmapHierarchyTaskSpec
    prepared: _PreparedFold


def _framed(digest: _DigestWriter, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, byteorder="big", signed=False))
    digest.update(value)


def _matrix_components(
    prepared: _PreparedFold,
    label: str,
) -> tuple[np.ndarray, tuple[str, ...], np.ndarray]:
    selected = tuple(
        record for record in prepared.training_records if record.modeled_label == label
    )
    indices = np.asarray(prepared.feature_indices, dtype=np.int64)
    counts = np.stack(
        tuple(np.asarray(record.gene_counts[indices], dtype=np.int64) for record in selected)
    )
    studies = tuple(record.study_key for record in selected)
    return counts, studies, np.asarray(prepared.background, dtype=np.float64)


def _selected_feature_axis_digest(
    feature_order_digest: Sha256Digest,
    feature_indices: tuple[int, ...],
) -> Sha256Digest:
    return sha256_digest(
        {
            "schema": FEATURE_AXIS_SCHEMA,
            "feature_order_digest": feature_order_digest,
            "feature_indices": list(feature_indices),
        }
    )


def _training_matrix_digest(
    prepared: _PreparedFold,
    label: str,
    selected_axis_digest: Sha256Digest,
) -> Sha256Digest:
    counts, studies, background = _matrix_components(prepared, label)
    order = sorted(
        range(counts.shape[0]),
        key=lambda row: (studies[row], tuple(int(value) for value in counts[row])),
    )
    digest = hashlib.sha256()
    _framed(digest, TRAINING_MATRIX_SCHEMA.encode("utf-8"))
    _framed(digest, selected_axis_digest.encode("ascii"))
    _framed(digest, label.encode("utf-8"))
    _framed(digest, np.asarray(background, dtype="<f8").tobytes(order="C"))
    for row in order:
        _framed(digest, studies[row].encode("utf-8"))
        _framed(digest, np.asarray(counts[row], dtype="<i8").tobytes(order="C"))
    return "sha256:" + digest.hexdigest()


def _task_spec(
    prepared: _PreparedFold,
    label: str,
    shrinkage_index: int,
    shrinkage: float,
    feature_order_digest: Sha256Digest,
) -> GbmapHierarchyTaskSpec:
    selected_axis = _selected_feature_axis_digest(
        feature_order_digest,
        prepared.feature_indices,
    )
    matrix_digest = _training_matrix_digest(prepared, label, selected_axis)
    selected_records = tuple(
        record for record in prepared.training_records if record.modeled_label == label
    )
    body: dict[str, object] = {
        "fold_id": prepared.fold.fold_id,
        "kind": prepared.fold.kind,
        "shrinkage_index": shrinkage_index,
        "shrinkage": shrinkage,
        "modeled_label": label,
        "training_record_count": len(selected_records),
        "training_study_count": len({record.study_key for record in selected_records}),
        "selected_feature_count": len(prepared.feature_indices),
        "selected_feature_axis_digest": selected_axis,
        "training_matrix_digest": matrix_digest,
    }
    return GbmapHierarchyTaskSpec.model_validate(
        {"task_digest": sha256_digest({"schema": TASK_SCHEMA, **body}), **body}
    )


def _preparation_receipt(
    prepared: _PreparedFold | _AbstainedFold,
) -> GbmapFoldPreparationReceipt:
    if type(prepared) is _PreparedFold:
        return GbmapFoldPreparationReceipt(
            fold_id=prepared.fold.fold_id,
            kind=prepared.fold.kind,
            state="prepared",
            abstention_reason=None,
            eligible_lineage_count=len(prepared.labels),
            selected_feature_count=len(prepared.feature_indices),
        )
    if type(prepared) is _AbstainedFold:
        return GbmapFoldPreparationReceipt(
            fold_id=prepared.fold.fold_id,
            kind=prepared.fold.kind,
            state="abstained",
            abstention_reason=prepared.reason,
            eligible_lineage_count=prepared.eligible_lineage_count,
            selected_feature_count=prepared.selected_feature_count,
        )
    raise ValueError("GBmap fold preparation type is not exact")


def _build_manifest_and_tasks(
    extraction: GbmapExtractionResult,
    plan: ValidationSplitPlan,
    preflight: preflight_driver.GbmapDevelopmentPreflightReceipt,
    configuration: TrainingConfiguration = DEFAULT_TRAINING_CONFIGURATION,
) -> tuple[GbmapHierarchyRunManifest, tuple[_RuntimeTask, ...]]:
    if type(extraction) is not GbmapExtractionResult or type(plan) is not ValidationSplitPlan:
        raise ValueError("GBmap hierarchy inputs are not exact internal types")
    if type(configuration) is not TrainingConfiguration:
        raise ValueError("GBmap hierarchy configuration type is not exact")
    expected_preflight = preflight_driver._build_receipt(
        extraction,
        plan,
        extraction.receipt.source_sha256,
    )
    if preflight != expected_preflight:
        raise ValueError("GBmap hierarchy source does not match the structural preflight")
    prepared_values = tuple(
        _prepare_fold(extraction.reference, plan, fold, None) for fold in plan.folds
    )
    feature_digest = extraction.reference.feature_order_digest
    runtime_tasks: list[_RuntimeTask] = []
    for prepared in prepared_values:
        if type(prepared) is not _PreparedFold:
            continue
        for shrinkage_index, shrinkage in enumerate(configuration.shrinkage_grid):
            runtime_tasks.extend(
                _RuntimeTask(
                    spec=_task_spec(
                        prepared,
                        label,
                        shrinkage_index,
                        shrinkage,
                        feature_digest,
                    ),
                    prepared=prepared,
                )
                for label in prepared.labels
            )
    runtime = tuple(
        sorted(
            runtime_tasks,
            key=lambda task: (
                task.spec.fold_id,
                task.spec.shrinkage_index,
                task.spec.modeled_label,
            ),
        )
    )
    specs = tuple(task.spec for task in runtime)
    preparation = tuple(
        sorted(
            (_preparation_receipt(item) for item in prepared_values),
            key=lambda item: item.fold_id,
        )
    )
    profile = development_profile()
    split_digest = sha256_digest(preflight.validation_split_receipt.model_dump(mode="json"))
    inventory_digest = sha256_digest(
        {
            "schema": TASK_INVENTORY_SCHEMA,
            "tasks": [task.model_dump(mode="json") for task in specs],
        }
    )
    body: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA,
        "run_state": "development_validation_hierarchy_tasks_only",
        "reviewed_sha256": extraction.receipt.source_sha256,
        "source_bytes": extraction.receipt.source_bytes,
        "taxonomy_digest": extraction.receipt.taxonomy_digest,
        "extraction_recipe_digest": extraction.receipt.extraction_recipe_digest,
        "extraction_receipt_digest": extraction.receipt.receipt_digest,
        "preflight_receipt_digest": preflight.receipt_digest,
        "preflight_task_dimensions_digest": preflight.task_dimensions_digest,
        "profile_id": profile.profile_id,
        "profile_digest": profile.profile_digest,
        "engine_semantic_digest": profile.engine_semantic_digest,
        "training_configuration_digest": preflight_driver.training_configuration_digest(
            configuration
        ),
        "split_receipt_digest": split_digest,
        "feature_order_digest": feature_digest,
        "preparation_receipts": [item.model_dump(mode="json") for item in preparation],
        "task_inventory_digest": inventory_digest,
        "task_count": len(specs),
        "preflight_hierarchy_fit_upper_bound": (
            preflight.task_summary.validation_hierarchy_fit_upper_bound
        ),
        "tasks": [item.model_dump(mode="json") for item in specs],
        "source_admission_granted": False,
        "final_model_fitted": False,
        "model_artifact_emitted": False,
        "production_artifact_permitted": False,
        "runtime_mount_permitted": False,
        "public_http_mounted": False,
        "public_cli_mounted": False,
        "source_path_retained": False,
        "donor_identifiers_retained": False,
        "donor_hashes_retained": False,
        "donor_profiles_retained": False,
        "feature_identities_retained": False,
        "raw_material_retained": False,
    }
    manifest = GbmapHierarchyRunManifest.model_validate(
        {
            "manifest_digest": sha256_digest(body),
            **body,
            "preparation_receipts": preparation,
            "tasks": specs,
        }
    )
    return manifest, runtime


def _fit_semantic_digest(value: LineageHierarchyFit) -> Sha256Digest:
    return sha256_digest(
        {
            "schema": HIERARCHY_FIT_DIGEST_SCHEMA,
            "study_keys": list(value.study_keys),
            "study_signatures": [[float(item) for item in row] for row in value.study_signatures],
            "global_signature": [float(item) for item in value.global_signature],
            "concentration": value.concentration,
            "shrinkage": value.shrinkage,
            "initial_objective": value.initial_objective,
            "objective": value.objective,
            "converged": value.converged,
            "iterations": value.iterations,
            "kkt_residual": value.kkt_residual,
            "trace": [
                {
                    "iteration": item.iteration,
                    "objective": item.objective,
                    "concentration": item.concentration,
                    "relative_objective_change": item.relative_objective_change,
                    "maximum_signature_l1_change": item.maximum_signature_l1_change,
                    "kkt_residual": item.kkt_residual,
                    "signature_updates": item.signature_updates,
                    "backtracking_steps": item.backtracking_steps,
                    "concentration_search_iterations": (item.concentration_search_iterations),
                }
                for item in value.trace
            ],
        }
    )


def _trace_digest(value: LineageHierarchyFit) -> Sha256Digest:
    return sha256_digest(
        {
            "schema": "gbmap-hierarchy-trace/1.0.0",
            "trace": [
                (
                    item.iteration,
                    item.objective,
                    item.concentration,
                    item.relative_objective_change,
                    item.maximum_signature_l1_change,
                    item.kkt_residual,
                    item.signature_updates,
                    item.backtracking_steps,
                    item.concentration_search_iterations,
                )
                for item in value.trace
            ],
        }
    )


def _evaluation_output(  # noqa: PLR0913
    *,
    state: TaskState,
    reason: TaskFailureReason | None,
    fit: LineageHierarchyFit | None,
    held_record_count: int = 0,
    held_study_count: int = 0,
    mean_per_count_nll: float | None = None,
) -> GbmapHierarchyEvaluationOutput:
    body: dict[str, object] = {
        "state": state,
        "abstention_reason": reason,
        "hierarchy_fit_digest": None if fit is None else _fit_semantic_digest(fit),
        "hierarchy_trace_digest": None if fit is None else _trace_digest(fit),
        "hierarchy_converged": None if fit is None else fit.converged,
        "hierarchy_iterations": None if fit is None else fit.iterations,
        "hierarchy_initial_objective": None if fit is None else fit.initial_objective,
        "hierarchy_objective": None if fit is None else fit.objective,
        "hierarchy_kkt_residual": None if fit is None else fit.kkt_residual,
        "evaluated_held_record_count": held_record_count,
        "evaluated_held_study_count": held_study_count,
        "mean_per_count_nll": mean_per_count_nll,
    }
    return GbmapHierarchyEvaluationOutput.model_validate(
        {
            "evaluation_output_digest": sha256_digest({"schema": EVALUATION_OUTPUT_SCHEMA, **body}),
            **body,
        }
    )


def _held_score(
    task: _RuntimeTask,
    fit: LineageHierarchyFit,
) -> tuple[int, int, float] | None:
    indices = np.asarray(task.prepared.feature_indices, dtype=np.int64)
    scores_by_study: dict[str, list[float]] = {}
    for record in task.prepared.held_records:
        if record.modeled_label != task.spec.modeled_label:
            continue
        counts = np.asarray(record.gene_counts[indices], dtype=np.int64)
        if int(np.sum(counts, dtype=np.int64)) == 0:
            continue
        scores_by_study.setdefault(record.study_key, []).append(
            dirichlet_multinomial_per_count_nll(
                counts,
                fit.global_signature,
                fit.concentration,
            )
        )
    if not scores_by_study:
        return None
    study_scores = tuple(
        math.fsum(scores_by_study[study]) / len(scores_by_study[study])
        for study in sorted(scores_by_study)
    )
    return (
        sum(len(scores) for scores in scores_by_study.values()),
        len(study_scores),
        math.fsum(study_scores) / len(study_scores),
    )


def _checkpoint_body(
    manifest: GbmapHierarchyRunManifest,
    spec: GbmapHierarchyTaskSpec,
    evaluation: GbmapHierarchyEvaluationOutput,
) -> dict[str, object]:
    return {
        "schema_version": CHECKPOINT_SCHEMA,
        "manifest_digest": manifest.manifest_digest,
        "task_digest": spec.task_digest,
        "fold_id": spec.fold_id,
        "kind": spec.kind,
        "shrinkage_index": spec.shrinkage_index,
        "shrinkage": spec.shrinkage,
        "modeled_label": spec.modeled_label,
        "reviewed_sha256": manifest.reviewed_sha256,
        "profile_digest": manifest.profile_digest,
        "engine_semantic_digest": manifest.engine_semantic_digest,
        "training_configuration_digest": manifest.training_configuration_digest,
        "split_receipt_digest": manifest.split_receipt_digest,
        "feature_order_digest": manifest.feature_order_digest,
        "selected_feature_axis_digest": spec.selected_feature_axis_digest,
        "training_matrix_digest": spec.training_matrix_digest,
        "evaluation": evaluation.model_dump(mode="json"),
        "source_admission_granted": False,
        "final_model_fitted": False,
        "model_artifact_emitted": False,
        "production_artifact_permitted": False,
        "runtime_mount_permitted": False,
        "public_http_mounted": False,
        "public_cli_mounted": False,
        "source_path_retained": False,
        "donor_identifiers_retained": False,
        "donor_hashes_retained": False,
        "donor_profiles_retained": False,
        "feature_identities_retained": False,
        "raw_material_retained": False,
    }


def _execute_task(
    manifest: GbmapHierarchyRunManifest,
    task: _RuntimeTask,
    configuration: TrainingConfiguration = DEFAULT_TRAINING_CONFIGURATION,
) -> GbmapHierarchyCheckpoint:
    spec = task.spec
    try:
        fit = _fit_label(
            task.prepared.training_records,
            label=spec.modeled_label,
            feature_indices=task.prepared.feature_indices,
            background=task.prepared.background,
            shrinkage=spec.shrinkage,
            configuration=configuration.hierarchy,
            cancellation=None,
        )
    except (GbmapInputError, GbmapNumericalError, ValueError):
        evaluation = _evaluation_output(
            state="abstained",
            reason="hierarchy_fit_failed",
            fit=None,
        )
    else:
        if not verify_hierarchy_trace(fit):
            evaluation = _evaluation_output(
                state="abstained",
                reason="hierarchy_trace_invalid",
                fit=fit,
            )
        elif not fit.converged:
            evaluation = _evaluation_output(
                state="abstained",
                reason="hierarchy_did_not_converge",
                fit=fit,
            )
        else:
            held = _held_score(task, fit)
            if held is None:
                evaluation = _evaluation_output(
                    state="abstained",
                    reason="no_positive_held_marker_counts",
                    fit=fit,
                )
            else:
                held_records, held_studies, score = held
                evaluation = _evaluation_output(
                    state="evaluated",
                    reason=None,
                    fit=fit,
                    held_record_count=held_records,
                    held_study_count=held_studies,
                    mean_per_count_nll=score,
                )
    body = _checkpoint_body(manifest, spec, evaluation)
    return GbmapHierarchyCheckpoint.model_validate(
        {
            "checkpoint_digest": sha256_digest(body),
            **body,
            "evaluation": evaluation,
        }
    )


def _positive_held_dimensions(task: _RuntimeTask) -> tuple[int, int]:
    indices = np.asarray(task.prepared.feature_indices, dtype=np.int64)
    studies: set[str] = set()
    count = 0
    for record in task.prepared.held_records:
        if record.modeled_label != task.spec.modeled_label:
            continue
        selected = np.asarray(record.gene_counts[indices], dtype=np.int64)
        if int(np.sum(selected, dtype=np.int64)) > 0:
            count += 1
            studies.add(record.study_key)
    return count, len(studies)


def _validate_runtime_task_binding(
    checkpoint: GbmapHierarchyCheckpoint,
    manifest: GbmapHierarchyRunManifest,
    runtime: _RuntimeTask,
) -> None:
    spec = runtime.spec
    selected_axis = _selected_feature_axis_digest(
        manifest.feature_order_digest,
        runtime.prepared.feature_indices,
    )
    matrix_digest = _training_matrix_digest(
        runtime.prepared,
        spec.modeled_label,
        selected_axis,
    )
    if (
        selected_axis != spec.selected_feature_axis_digest
        or matrix_digest != spec.training_matrix_digest
    ):
        raise ValueError("GBmap hierarchy runtime matrix does not replay its task")
    held_records, held_studies = _positive_held_dimensions(runtime)
    evaluation = checkpoint.evaluation
    if evaluation.state == "evaluated" and (
        evaluation.evaluated_held_record_count != held_records
        or evaluation.evaluated_held_study_count != held_studies
    ):
        raise ValueError("GBmap hierarchy held-evidence dimensions do not replay")
    if evaluation.abstention_reason == "no_positive_held_marker_counts" and (
        held_records != 0 or held_studies != 0
    ):
        raise ValueError("GBmap hierarchy held-evidence abstention does not replay")


def _validate_checkpoint_binding(
    checkpoint: GbmapHierarchyCheckpoint,
    manifest: GbmapHierarchyRunManifest,
    spec: GbmapHierarchyTaskSpec,
    runtime: _RuntimeTask | None,
) -> None:
    repeated = (
        checkpoint.manifest_digest,
        checkpoint.task_digest,
        checkpoint.fold_id,
        checkpoint.kind,
        checkpoint.shrinkage_index,
        checkpoint.shrinkage,
        checkpoint.modeled_label,
        checkpoint.reviewed_sha256,
        checkpoint.profile_digest,
        checkpoint.engine_semantic_digest,
        checkpoint.training_configuration_digest,
        checkpoint.split_receipt_digest,
        checkpoint.feature_order_digest,
        checkpoint.selected_feature_axis_digest,
        checkpoint.training_matrix_digest,
    )
    expected = (
        manifest.manifest_digest,
        spec.task_digest,
        spec.fold_id,
        spec.kind,
        spec.shrinkage_index,
        spec.shrinkage,
        spec.modeled_label,
        manifest.reviewed_sha256,
        manifest.profile_digest,
        manifest.engine_semantic_digest,
        manifest.training_configuration_digest,
        manifest.split_receipt_digest,
        manifest.feature_order_digest,
        spec.selected_feature_axis_digest,
        spec.training_matrix_digest,
    )
    if repeated != expected:
        raise ValueError("GBmap hierarchy checkpoint provenance does not bind its task")
    if runtime is not None:
        _validate_runtime_task_binding(checkpoint, manifest, runtime)


def canonical_manifest_bytes(manifest: GbmapHierarchyRunManifest) -> bytes:
    if type(manifest) is not GbmapHierarchyRunManifest:
        raise GbmapHierarchyTaskDriverError("GBmap hierarchy manifest type is not exact")
    payload = canonical_json_bytes(manifest) + b"\n"
    if len(payload) > MAX_MANIFEST_BYTES:
        raise GbmapHierarchyTaskDriverError("GBmap hierarchy manifest exceeds its size bound")
    return payload


def canonical_checkpoint_bytes(checkpoint: GbmapHierarchyCheckpoint) -> bytes:
    if type(checkpoint) is not GbmapHierarchyCheckpoint:
        raise GbmapHierarchyTaskDriverError("GBmap hierarchy checkpoint type is not exact")
    payload = canonical_json_bytes(checkpoint) + b"\n"
    if len(payload) > MAX_CHECKPOINT_BYTES:
        raise GbmapHierarchyTaskDriverError("GBmap hierarchy checkpoint exceeds its size bound")
    return payload


def canonical_batch_receipt_bytes(receipt: GbmapHierarchyBatchReceipt) -> bytes:
    if type(receipt) is not GbmapHierarchyBatchReceipt:
        raise GbmapHierarchyTaskDriverError("GBmap hierarchy batch receipt type is not exact")
    return canonical_json_bytes(receipt) + b"\n"


def validate_manifest_json_bytes(payload: bytes) -> GbmapHierarchyRunManifest:
    if type(payload) is not bytes or not payload or len(payload) > MAX_MANIFEST_BYTES:
        raise GbmapHierarchyTaskDriverError("GBmap hierarchy manifest bytes are invalid")
    manifest = _privacy_call(
        "GBmap hierarchy manifest failed strict validation",
        lambda: GbmapHierarchyRunManifest.model_validate_json(payload),
    )
    if payload != canonical_manifest_bytes(manifest):
        raise GbmapHierarchyTaskDriverError("GBmap hierarchy manifest is not canonical")
    return manifest


def validate_checkpoint_json_bytes(payload: bytes) -> GbmapHierarchyCheckpoint:
    if type(payload) is not bytes or not payload or len(payload) > MAX_CHECKPOINT_BYTES:
        raise GbmapHierarchyTaskDriverError("GBmap hierarchy checkpoint bytes are invalid")
    checkpoint = _privacy_call(
        "GBmap hierarchy checkpoint failed strict validation",
        lambda: GbmapHierarchyCheckpoint.model_validate_json(payload),
    )
    if payload != canonical_checkpoint_bytes(checkpoint):
        raise GbmapHierarchyTaskDriverError("GBmap hierarchy checkpoint is not canonical")
    return checkpoint


def _read_regular_bytes(path: Path, maximum: int, message: str) -> bytes:
    def read() -> bytes:
        info = path.lstat()
        if (
            fit_driver._is_link_or_reparse(info)
            or not stat.S_ISREG(info.st_mode)
            or info.st_size < 1
            or info.st_size > maximum
        ):
            raise ValueError("file boundary is invalid")
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if fit_driver._file_identity(opened) != fit_driver._file_identity(info):
                raise ValueError("file identity changed")
            payload = stream.read(maximum + 1)
        if len(payload) != info.st_size:
            raise ValueError("file length changed")
        return payload

    return _privacy_call(message, read)


def _inspect_private_directory(path: Path) -> Path:
    if not isinstance(path, Path):
        raise GbmapHierarchyTaskDriverError("run directory must be a pathlib Path")
    lexical = _privacy_call(
        "GBmap hierarchy run directory could not be normalized safely",
        lambda: fit_driver._lexical_absolute(path),
    )
    if fit_driver._is_within(lexical, fit_driver._REPOSITORY_ROOT):
        raise GbmapHierarchyTaskDriverError(
            "GBmap hierarchy run directory must remain outside the repository"
        )
    _privacy_call(
        "GBmap hierarchy run directory could not be prepared safely",
        lambda: lexical.mkdir(parents=True, exist_ok=True),
    )
    chain: list[Path] = [lexical]
    cursor = lexical.parent
    while True:
        chain.append(cursor)
        if cursor == cursor.parent:
            break
        cursor = cursor.parent
    records = _privacy_call(
        "GBmap hierarchy run directory could not be inspected safely",
        lambda: tuple(os.lstat(item) for item in chain),
    )
    if any(
        fit_driver._is_link_or_reparse(info) or not stat.S_ISDIR(info.st_mode) for info in records
    ):
        raise GbmapHierarchyTaskDriverError(
            "GBmap hierarchy run directory must use ordinary non-reparse ancestors"
        )
    return lexical


def _checkpoint_filename(checkpoint: GbmapHierarchyCheckpoint) -> str:
    return (
        checkpoint.task_digest.removeprefix("sha256:")
        + "."
        + checkpoint.checkpoint_digest.removeprefix("sha256:")
        + ".json"
    )


def _load_manifest_if_present(run_directory: Path) -> GbmapHierarchyRunManifest | None:
    path = run_directory / MANIFEST_NAME
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        raise GbmapHierarchyTaskDriverError(
            "GBmap hierarchy manifest could not be inspected"
        ) from None
    payload = _read_regular_bytes(
        path,
        MAX_MANIFEST_BYTES,
        "GBmap hierarchy manifest could not be read safely",
    )
    return validate_manifest_json_bytes(payload)


def _load_checkpoints(
    run_directory: Path,
    manifest: GbmapHierarchyRunManifest,
    runtime_by_digest: dict[Sha256Digest, _RuntimeTask] | None,
) -> dict[Sha256Digest, GbmapHierarchyCheckpoint]:
    directory = run_directory / CHECKPOINT_DIRECTORY_NAME
    try:
        directory.mkdir(exist_ok=True)
        info = directory.lstat()
    except OSError:
        raise GbmapHierarchyTaskDriverError(
            "GBmap hierarchy checkpoint directory could not be prepared"
        ) from None
    if fit_driver._is_link_or_reparse(info) or not stat.S_ISDIR(info.st_mode):
        raise GbmapHierarchyTaskDriverError(
            "GBmap hierarchy checkpoint directory must be ordinary and non-reparse"
        )
    task_by_digest = {task.task_digest: task for task in manifest.tasks}
    retained: dict[Sha256Digest, GbmapHierarchyCheckpoint] = {}
    entries = _privacy_call(
        "GBmap hierarchy checkpoint inventory could not be inspected",
        lambda: tuple(sorted(directory.iterdir(), key=lambda item: item.name)),
    )
    for path in entries:
        if _CHECKPOINT_NAME_PATTERN.fullmatch(path.name) is None:
            raise GbmapHierarchyTaskDriverError(
                "GBmap hierarchy checkpoint inventory contains an unexpected entry"
            )
        payload = _read_regular_bytes(
            path,
            MAX_CHECKPOINT_BYTES,
            "GBmap hierarchy checkpoint could not be read safely",
        )
        checkpoint = validate_checkpoint_json_bytes(payload)
        if path.name != _checkpoint_filename(checkpoint):
            raise GbmapHierarchyTaskDriverError(
                "GBmap hierarchy checkpoint filename is not content-addressed"
            )
        spec = task_by_digest.get(checkpoint.task_digest)
        if spec is None or checkpoint.task_digest in retained:
            raise GbmapHierarchyTaskDriverError(
                "GBmap hierarchy checkpoint task inventory is invalid"
            )
        runtime = (
            None if runtime_by_digest is None else runtime_by_digest.get(checkpoint.task_digest)
        )
        if runtime_by_digest is not None and runtime is None:
            raise GbmapHierarchyTaskDriverError(
                "GBmap hierarchy checkpoint has no deterministic runtime task"
            )
        _privacy_call(
            "GBmap hierarchy checkpoint failed provenance replay",
            partial(_validate_checkpoint_binding, checkpoint, manifest, spec, runtime),
        )
        retained[checkpoint.task_digest] = checkpoint
    return retained


def _publish_manifest(
    run_directory: Path,
    source: Path,
    manifest: GbmapHierarchyRunManifest,
) -> None:
    payload = canonical_manifest_bytes(manifest)
    _privacy_call(
        "GBmap hierarchy manifest publication failed closed",
        lambda: write_receipt(run_directory / MANIFEST_NAME, payload, source=source),
    )


def _publish_checkpoint(
    run_directory: Path,
    source: Path,
    checkpoint: GbmapHierarchyCheckpoint,
) -> None:
    payload = canonical_checkpoint_bytes(checkpoint)
    destination = run_directory / CHECKPOINT_DIRECTORY_NAME / _checkpoint_filename(checkpoint)
    _privacy_call(
        "GBmap hierarchy checkpoint publication failed closed",
        lambda: write_receipt(destination, payload, source=source),
    )


def _batch_receipt(
    manifest: GbmapHierarchyRunManifest,
    before: int,
    executed: tuple[GbmapHierarchyCheckpoint, ...],
    max_tasks: int,
    *,
    dry_run: bool,
) -> GbmapHierarchyBatchReceipt:
    after = before + len(executed)
    body: dict[str, object] = {
        "schema_version": BATCH_RECEIPT_SCHEMA,
        "manifest_digest": manifest.manifest_digest,
        "task_count": manifest.task_count,
        "verified_checkpoint_count_before": before,
        "executed_task_count": len(executed),
        "verified_checkpoint_count_after": after,
        "remaining_task_count": manifest.task_count - after,
        "max_tasks": max_tasks,
        "dry_run": dry_run,
        "run_complete": after == manifest.task_count,
        "checkpoint_digests": [item.checkpoint_digest for item in executed],
        "source_admission_granted": False,
        "final_model_fitted": False,
        "model_artifact_emitted": False,
        "production_artifact_permitted": False,
        "runtime_mount_permitted": False,
        "public_http_mounted": False,
        "public_cli_mounted": False,
    }
    return GbmapHierarchyBatchReceipt.model_validate(
        {
            "receipt_digest": sha256_digest(body),
            **body,
            "checkpoint_digests": tuple(item.checkpoint_digest for item in executed),
        }
    )


def run_batch(  # noqa: PLR0913
    source: Path,
    reviewed_sha256: str,
    preflight_path: Path,
    run_directory: Path,
    *,
    max_tasks: int,
    dry_run: bool = False,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> GbmapHierarchyBatchReceipt:
    """Re-extract, verify existing state, and execute a bounded pending prefix."""

    fit_driver._require_acknowledgements(
        development_only_acknowledged=development_only_acknowledged,
        sha256_independently_reviewed=sha256_independently_reviewed,
    )
    reviewed = fit_driver._reviewed_sha256(reviewed_sha256)
    if type(max_tasks) is not int or not 1 <= max_tasks <= MAX_TASKS_PER_BATCH:
        raise GbmapHierarchyTaskDriverError(
            f"max_tasks must be an exact integer from 1 through {MAX_TASKS_PER_BATCH}"
        )
    preflight_payload = _read_regular_bytes(
        preflight_path,
        MAX_PREFLIGHT_BYTES,
        "GBmap structural preflight receipt could not be read safely",
    )
    preflight = preflight_driver.validate_preflight_json_bytes(preflight_payload)
    if preflight.reviewed_sha256 != reviewed:
        raise GbmapHierarchyTaskDriverError(
            "GBmap structural preflight does not bind the reviewed source digest"
        )
    private_directory = _inspect_private_directory(run_directory)
    existing_manifest = _load_manifest_if_present(private_directory)
    if existing_manifest is None:
        checkpoint_directory = private_directory / CHECKPOINT_DIRECTORY_NAME
        if checkpoint_directory.exists() and any(checkpoint_directory.iterdir()):
            raise GbmapHierarchyTaskDriverError(
                "GBmap hierarchy checkpoints cannot exist without a run manifest"
            )
    else:
        _load_checkpoints(private_directory, existing_manifest, None)

    before_snapshot = fit_driver._capture_source_snapshot(source)
    if fit_driver._is_within(before_snapshot.lexical_path, private_directory):
        raise GbmapHierarchyTaskDriverError(
            "GBmap hierarchy source must remain outside its run directory"
        )
    guard = fit_driver._open_source_guard(before_snapshot)
    try:
        lock = fit_driver._production_lock(reviewed)
        dependencies = _privacy_call(
            "production GBmap hierarchy dependencies failed closed",
            lambda: (
                production_extraction_recipe(),
                production_donor_crosswalk(),
                production_study_crosswalk(),
                production_label_taxonomy(),
            ),
        )
        recipe, donor_crosswalk, study_crosswalk, taxonomy = dependencies
        extraction = _privacy_call(
            "GBmap hierarchy source extraction failed closed",
            lambda: extract_pinned_gbmap_reference(
                source,
                lock=lock,
                taxonomy=taxonomy,
                donor_crosswalk=donor_crosswalk,
                study_crosswalk=study_crosswalk,
                recipe=recipe,
            ),
        )
        plan = _privacy_call(
            "GBmap hierarchy split planning failed closed",
            lambda: build_validation_split_plan(extraction.reference),
        )
        manifest, runtime_tasks = _privacy_call(
            "GBmap hierarchy task manifest construction failed closed",
            lambda: _build_manifest_and_tasks(extraction, plan, preflight),
        )
        after_extraction = fit_driver._capture_source_snapshot(source)
        fit_driver._require_source_unchanged(before_snapshot, after_extraction, guard)
        if existing_manifest is not None and existing_manifest != manifest:
            raise GbmapHierarchyTaskDriverError(
                "GBmap hierarchy run manifest does not match deterministic replay"
            )
        _publish_manifest(private_directory, source, manifest)
        runtime_by_digest = {task.spec.task_digest: task for task in runtime_tasks}
        checkpoints = _load_checkpoints(
            private_directory,
            manifest,
            runtime_by_digest,
        )
        pending = (
            ()
            if dry_run
            else tuple(task for task in runtime_tasks if task.spec.task_digest not in checkpoints)[
                :max_tasks
            ]
        )
        executed: list[GbmapHierarchyCheckpoint] = []
        for task in pending:
            checkpoint = _privacy_call(
                "GBmap hierarchy task execution failed closed",
                partial(_execute_task, manifest, task),
            )
            current_snapshot = fit_driver._capture_source_snapshot(source)
            fit_driver._require_source_unchanged(before_snapshot, current_snapshot, guard)
            _privacy_call(
                "GBmap hierarchy checkpoint failed numerical replay",
                partial(
                    _validate_checkpoint_binding,
                    checkpoint,
                    manifest,
                    task.spec,
                    task,
                ),
            )
            _publish_checkpoint(private_directory, source, checkpoint)
            executed.append(checkpoint)
        final_snapshot = fit_driver._capture_source_snapshot(source)
        fit_driver._require_source_unchanged(before_snapshot, final_snapshot, guard)
        return _batch_receipt(
            manifest,
            len(checkpoints),
            tuple(executed),
            max_tasks,
            dry_run=dry_run,
        )
    finally:
        with suppress(OSError):
            guard.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="exact local scarches_core_GBmap.h5ad path")
    parser.add_argument(
        "--reviewed-sha256",
        required=True,
        help="independently reviewed canonical sha256:<64 lowercase hex> lock",
    )
    parser.add_argument(
        "--preflight",
        required=True,
        type=Path,
        help="canonical structural-preflight receipt",
    )
    parser.add_argument(
        "--run-directory",
        required=True,
        type=Path,
        help="private outside-repository immutable run directory",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=1,
        help=f"bounded pending task count, from 1 through {MAX_TASKS_PER_BATCH}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="verify and publish the exact task schedule without executing a hierarchy",
    )
    parser.add_argument("--acknowledge-development-only", required=True, action="store_true")
    parser.add_argument(
        "--acknowledge-sha256-independently-reviewed",
        required=True,
        action="store_true",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = run_batch(
            cast("Path", args.source),
            cast("str", args.reviewed_sha256),
            cast("Path", args.preflight),
            cast("Path", args.run_directory),
            max_tasks=cast("int", args.max_tasks),
            dry_run=cast("bool", args.dry_run),
            development_only_acknowledged=cast("bool", args.acknowledge_development_only),
            sha256_independently_reviewed=cast(
                "bool",
                args.acknowledge_sha256_independently_reviewed,
            ),
        )
        sys.stdout.write(canonical_batch_receipt_bytes(receipt).decode("utf-8"))
    except (
        GbmapHierarchyTaskDriverError,
        fit_driver.GbmapDevelopmentFitDriverError,
        GbmapDeconvolutionError,
        OSError,
        TypeError,
        ValueError,
    ):
        sys.stderr.write("error: GBmap hierarchy task batch failed closed\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

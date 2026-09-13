"""Run exact GBmap extraction and split planning without fitting a model.

This maintainer-only command keeps the source and transient donor aggregates
outside the repository.  Its only durable output is a canonical, deidentified
receipt proving exact extraction, deterministic validation planning, and an
upper bound on the hierarchy tasks that a later fitted run could attempt.
"""

# ruff: noqa: TRY003

from __future__ import annotations

import argparse
import sys
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Self, cast

from pydantic import Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.gbmap_deconvolution import (
    DEFAULT_TRAINING_CONFIGURATION,
    PRODUCTION_SOURCE_LABELS,
    DeidentifiedValidationFoldReceipt,
    GbmapDeconvolutionError,
    GbmapExtractionReceipt,
    GbmapExtractionResult,
    LabelFoldSupport,
    TrainingConfiguration,
    ValidationKind,
    ValidationSplitPlan,
    ValidationSplitReceipt,
    build_validation_split_plan,
    development_profile,
    extract_pinned_gbmap_reference,
    production_donor_crosswalk,
    production_extraction_recipe,
    production_label_taxonomy,
    production_reduction_recipe_digest,
    production_study_crosswalk,
)
from tools.capture_gbmap_source_admission import write_receipt
from tools.fit_gbmap_development_candidate import (
    GbmapDevelopmentFitDriverError,
    _capture_source_snapshot,
    _open_source_guard,
    _privacy_call,
    _production_lock,
    _require_acknowledgements,
    _require_source_unchanged,
    _reviewed_sha256,
)

OUTPUT_SCHEMA: Final = "glio-proteogen.gbmap-development-preflight-receipt/1.0.0"
CONFIGURATION_SCHEMA: Final = "gbmap-development-training-configuration/0.1.0-dev"
TASK_DIMENSION_SCHEMA: Final = "gbmap-development-task-dimensions/1.0.0"
MAX_OUTPUT_BYTES: Final = 4 * 1024 * 1024

PreflightState = Literal["structural_extraction_complete_training_not_run"]


class GbmapPreflightLabelSupport(FrozenModel):
    """Exact deidentified projection of one label's split support."""

    modeled_label: str = Field(min_length=1, max_length=256)
    training_usable_donor_count: int = Field(ge=0)
    training_usable_study_count: int = Field(ge=0)
    held_usable_donor_count: int = Field(ge=0)
    held_usable_study_count: int = Field(ge=0)
    evaluable: bool
    abstention_reasons: tuple[str, ...]

    def to_domain(self) -> LabelFoldSupport:
        return LabelFoldSupport(**self.model_dump(mode="python"))

    @model_validator(mode="after")
    def support_is_valid(self) -> Self:
        self.to_domain()
        return self


class GbmapPreflightSplitFold(FrozenModel):
    """Exact deidentified projection of one deterministic validation fold."""

    fold_id: str = Field(pattern=r"^(?:whole-study|within-study-donor)-[0-9]{4}$")
    kind: ValidationKind
    training_study_keys: tuple[str, ...]
    held_study_keys: tuple[str, ...]
    training_donor_count: int = Field(ge=0)
    held_donor_count: int = Field(gt=0)
    label_support: tuple[GbmapPreflightLabelSupport, ...] = Field(min_length=1)
    evaluable: bool
    abstention_reasons: tuple[str, ...]

    def to_domain(self) -> DeidentifiedValidationFoldReceipt:
        return DeidentifiedValidationFoldReceipt(
            fold_id=self.fold_id,
            kind=self.kind,
            training_study_keys=self.training_study_keys,
            held_study_keys=self.held_study_keys,
            training_donor_count=self.training_donor_count,
            held_donor_count=self.held_donor_count,
            label_support=tuple(item.to_domain() for item in self.label_support),
            evaluable=self.evaluable,
            abstention_reasons=self.abstention_reasons,
        )

    @model_validator(mode="after")
    def fold_is_valid(self) -> Self:
        self.to_domain()
        return self


class GbmapPreflightSplitReceipt(FrozenModel):
    """Strict JSON-safe form of the existing validation split receipt."""

    source_file_sha256: Sha256Digest
    source_bytes: int = Field(gt=0)
    taxonomy_digest: Sha256Digest
    extraction_recipe_digest: Sha256Digest
    folds: tuple[GbmapPreflightSplitFold, ...] = Field(min_length=1)

    def to_domain(self) -> ValidationSplitReceipt:
        return ValidationSplitReceipt(
            source_file_sha256=self.source_file_sha256,
            source_bytes=self.source_bytes,
            taxonomy_digest=self.taxonomy_digest,
            extraction_recipe_digest=self.extraction_recipe_digest,
            folds=tuple(item.to_domain() for item in self.folds),
        )

    @model_validator(mode="after")
    def receipt_is_valid(self) -> Self:
        self.to_domain()
        return self


class GbmapPreflightFoldDimension(FrozenModel):
    """Non-identifying computational dimensions for one planned fold."""

    fold_id: str = Field(pattern=r"^(?:whole-study|within-study-donor)-[0-9]{4}$")
    kind: ValidationKind
    evaluable: bool
    label_support_count: int = Field(gt=0)
    evaluable_label_count: int = Field(ge=0)
    training_donor_count: int = Field(ge=0)
    held_donor_count: int = Field(gt=0)
    hierarchy_fit_upper_bound_per_shrinkage: int = Field(ge=0)

    @model_validator(mode="after")
    def dimension_is_consistent(self) -> Self:
        expected = self.evaluable_label_count if self.evaluable else 0
        if self.evaluable_label_count > self.label_support_count:
            raise ValueError("evaluable label count exceeds split support")
        if self.hierarchy_fit_upper_bound_per_shrinkage != expected:
            raise ValueError("fold hierarchy upper bound does not match split support")
        return self


class GbmapPreflightTaskSummary(FrozenModel):
    """Aggregate, deidentified upper bounds before marker selection or fitting."""

    validation_fold_count: int = Field(gt=0)
    whole_study_fold_count: int = Field(ge=0)
    within_study_donor_fold_count: int = Field(ge=0)
    evaluable_fold_count: int = Field(ge=0)
    abstained_fold_count: int = Field(ge=0)
    modeled_label_count: int = Field(gt=0)
    shrinkage_candidate_count: int = Field(gt=0)
    candidate_fold_evaluation_count: int = Field(gt=0)
    evaluable_candidate_fold_count: int = Field(ge=0)
    evaluable_label_fold_count: int = Field(ge=0)
    validation_hierarchy_fit_upper_bound: int = Field(ge=0)
    final_lineage_fit_upper_bound: int = Field(gt=0)
    total_hierarchy_fit_upper_bound: int = Field(gt=0)

    @model_validator(mode="after")
    def summary_is_consistent(self) -> Self:
        if self.whole_study_fold_count + self.within_study_donor_fold_count != (
            self.validation_fold_count
        ):
            raise ValueError("validation fold-family counts do not reconcile")
        if self.evaluable_fold_count + self.abstained_fold_count != self.validation_fold_count:
            raise ValueError("validation fold-state counts do not reconcile")
        if self.candidate_fold_evaluation_count != (
            self.validation_fold_count * self.shrinkage_candidate_count
        ):
            raise ValueError("candidate-fold evaluation count does not reconcile")
        if self.evaluable_candidate_fold_count != (
            self.evaluable_fold_count * self.shrinkage_candidate_count
        ):
            raise ValueError("evaluable candidate-fold count does not reconcile")
        if self.validation_hierarchy_fit_upper_bound != (
            self.evaluable_label_fold_count * self.shrinkage_candidate_count
        ):
            raise ValueError("validation hierarchy upper bound does not reconcile")
        if self.final_lineage_fit_upper_bound != self.modeled_label_count:
            raise ValueError("final hierarchy upper bound does not reconcile")
        if self.total_hierarchy_fit_upper_bound != (
            self.validation_hierarchy_fit_upper_bound + self.final_lineage_fit_upper_bound
        ):
            raise ValueError("total hierarchy upper bound does not reconcile")
        return self


class GbmapDevelopmentPreflightReceipt(FrozenModel):
    """Immutable proof of structural extraction and split planning only."""

    schema_version: Literal["glio-proteogen.gbmap-development-preflight-receipt/1.0.0"] = (
        OUTPUT_SCHEMA
    )
    receipt_digest: Sha256Digest
    preflight_state: PreflightState = "structural_extraction_complete_training_not_run"
    reviewed_sha256: Sha256Digest
    profile_id: Literal["gbmap-dm-composition/0.1.0-dev"]
    profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    training_configuration_digest: Sha256Digest
    task_dimensions_digest: Sha256Digest
    extraction_receipt: GbmapExtractionReceipt
    validation_split_receipt: GbmapPreflightSplitReceipt
    fold_dimensions: tuple[GbmapPreflightFoldDimension, ...] = Field(min_length=1)
    task_summary: GbmapPreflightTaskSummary
    source_admission_granted: Literal[False] = False
    hierarchy_training_executed: Literal[False] = False
    model_fitted: Literal[False] = False
    model_parameters_retained: Literal[False] = False
    production_artifact_permitted: Literal[False] = False
    runtime_mount_permitted: Literal[False] = False
    public_http_mounted: Literal[False] = False
    public_cli_mounted: Literal[False] = False
    source_path_retained: Literal[False] = False
    cell_level_material_retained: Literal[False] = False
    donor_identifiers_retained: Literal[False] = False
    donor_hashes_retained: Literal[False] = False
    donor_profiles_retained: Literal[False] = False
    feature_identities_retained: Literal[False] = False
    aggregate_content_digest_retained: Literal[False] = False
    raw_material_retained: Literal[False] = False

    @model_validator(mode="after")
    def evidence_is_consistent(self) -> Self:
        _validate_receipt_semantics(self)
        payload = self.model_dump(mode="json", exclude={"receipt_digest"})
        if self.receipt_digest != sha256_digest(payload):
            raise ValueError("GBmap preflight receipt digest mismatch")
        return self


def _training_configuration_payload(configuration: TrainingConfiguration) -> dict[str, object]:
    if type(configuration) is not TrainingConfiguration:
        raise ValueError("GBmap preflight configuration type is not exact")
    hierarchy = configuration.hierarchy
    return {
        "schema": CONFIGURATION_SCHEMA,
        "shrinkage_grid": list(configuration.shrinkage_grid),
        "minimum_whole_study_folds": configuration.minimum_whole_study_folds,
        "minimum_within_study_donor_folds": configuration.minimum_within_study_donor_folds,
        "hierarchy": {
            "max_outer_iterations": hierarchy.max_outer_iterations,
            "max_study_sweeps": hierarchy.max_study_sweeps,
            "max_signature_iterations": hierarchy.max_signature_iterations,
            "max_backtracking_steps": hierarchy.max_backtracking_steps,
            "initial_signature_step": hierarchy.initial_signature_step,
            "maximum_signature_step": hierarchy.maximum_signature_step,
            "step_growth": hierarchy.step_growth,
            "backtracking_factor": hierarchy.backtracking_factor,
            "armijo_fraction": hierarchy.armijo_fraction,
            "inner_l1_tolerance": hierarchy.inner_l1_tolerance,
            "relative_objective_tolerance": hierarchy.relative_objective_tolerance,
            "simplex_l1_tolerance": hierarchy.simplex_l1_tolerance,
            "kkt_tolerance": hierarchy.kkt_tolerance,
            "objective_increase_tolerance": hierarchy.objective_increase_tolerance,
            "golden_log_tolerance": hierarchy.golden_log_tolerance,
            "max_golden_iterations": hierarchy.max_golden_iterations,
        },
    }


def training_configuration_digest(
    configuration: TrainingConfiguration = DEFAULT_TRAINING_CONFIGURATION,
) -> Sha256Digest:
    """Bind the exact candidate and hierarchy controls without executing them."""

    return sha256_digest(_training_configuration_payload(configuration))


def _project_label_support(value: LabelFoldSupport) -> GbmapPreflightLabelSupport:
    if type(value) is not LabelFoldSupport:
        raise ValueError("GBmap split support type is not exact")
    return GbmapPreflightLabelSupport(
        modeled_label=value.modeled_label,
        training_usable_donor_count=value.training_usable_donor_count,
        training_usable_study_count=value.training_usable_study_count,
        held_usable_donor_count=value.held_usable_donor_count,
        held_usable_study_count=value.held_usable_study_count,
        evaluable=value.evaluable,
        abstention_reasons=value.abstention_reasons,
    )


def _project_split_fold(
    value: DeidentifiedValidationFoldReceipt,
) -> GbmapPreflightSplitFold:
    if type(value) is not DeidentifiedValidationFoldReceipt:
        raise ValueError("GBmap split fold type is not exact")
    return GbmapPreflightSplitFold(
        fold_id=value.fold_id,
        kind=value.kind,
        training_study_keys=value.training_study_keys,
        held_study_keys=value.held_study_keys,
        training_donor_count=value.training_donor_count,
        held_donor_count=value.held_donor_count,
        label_support=tuple(_project_label_support(item) for item in value.label_support),
        evaluable=value.evaluable,
        abstention_reasons=value.abstention_reasons,
    )


def _project_split(value: ValidationSplitReceipt) -> GbmapPreflightSplitReceipt:
    if type(value) is not ValidationSplitReceipt:
        raise ValueError("GBmap split receipt type is not exact")
    return GbmapPreflightSplitReceipt(
        source_file_sha256=value.source_file_sha256,
        source_bytes=value.source_bytes,
        taxonomy_digest=value.taxonomy_digest,
        extraction_recipe_digest=value.extraction_recipe_digest,
        folds=tuple(_project_split_fold(item) for item in value.folds),
    )


def _fold_dimensions(
    split: ValidationSplitReceipt,
) -> tuple[GbmapPreflightFoldDimension, ...]:
    return tuple(
        GbmapPreflightFoldDimension(
            fold_id=fold.fold_id,
            kind=fold.kind,
            evaluable=fold.evaluable,
            label_support_count=len(fold.label_support),
            evaluable_label_count=sum(item.evaluable for item in fold.label_support),
            training_donor_count=fold.training_donor_count,
            held_donor_count=fold.held_donor_count,
            hierarchy_fit_upper_bound_per_shrinkage=(
                sum(item.evaluable for item in fold.label_support) if fold.evaluable else 0
            ),
        )
        for fold in split.folds
    )


def _task_summary(
    dimensions: tuple[GbmapPreflightFoldDimension, ...],
    split: ValidationSplitReceipt,
    configuration: TrainingConfiguration,
) -> GbmapPreflightTaskSummary:
    labels = {support.modeled_label for fold in split.folds for support in fold.label_support}
    shrinkage_count = len(configuration.shrinkage_grid)
    evaluable_folds = sum(item.evaluable for item in dimensions)
    evaluable_label_folds = sum(item.hierarchy_fit_upper_bound_per_shrinkage for item in dimensions)
    validation_upper_bound = evaluable_label_folds * shrinkage_count
    return GbmapPreflightTaskSummary(
        validation_fold_count=len(dimensions),
        whole_study_fold_count=sum(item.kind == "whole_study" for item in dimensions),
        within_study_donor_fold_count=sum(item.kind == "within_study_donor" for item in dimensions),
        evaluable_fold_count=evaluable_folds,
        abstained_fold_count=len(dimensions) - evaluable_folds,
        modeled_label_count=len(labels),
        shrinkage_candidate_count=shrinkage_count,
        candidate_fold_evaluation_count=len(dimensions) * shrinkage_count,
        evaluable_candidate_fold_count=evaluable_folds * shrinkage_count,
        evaluable_label_fold_count=evaluable_label_folds,
        validation_hierarchy_fit_upper_bound=validation_upper_bound,
        final_lineage_fit_upper_bound=len(labels),
        total_hierarchy_fit_upper_bound=validation_upper_bound + len(labels),
    )


def _task_dimensions_digest(
    dimensions: tuple[GbmapPreflightFoldDimension, ...],
    summary: GbmapPreflightTaskSummary,
    configuration_digest: Sha256Digest,
) -> Sha256Digest:
    return sha256_digest(
        {
            "schema": TASK_DIMENSION_SCHEMA,
            "training_configuration_digest": configuration_digest,
            "fold_dimensions": [item.model_dump(mode="json") for item in dimensions],
            "task_summary": summary.model_dump(mode="json"),
        }
    )


def _validate_production_receipts(
    extraction: GbmapExtractionReceipt,
    split: ValidationSplitReceipt,
) -> None:
    profile = development_profile()
    recipe = production_extraction_recipe()
    expected_inventory = (
        recipe.expected_cell_count,
        recipe.expected_cell_count,
        0,
        recipe.expected_source_donor_category_count,
        recipe.expected_grouped_donor_category_count,
        recipe.expected_source_study_category_count,
        recipe.expected_grouped_study_count,
        recipe.expected_source_label_count,
        len(PRODUCTION_SOURCE_LABELS),
    )
    observed_inventory = (
        extraction.cell_count,
        extraction.retained_cell_count,
        extraction.explicitly_excluded_cell_count,
        extraction.source_donor_category_count,
        extraction.grouped_donor_category_count,
        extraction.source_study_category_count,
        extraction.grouped_study_count,
        extraction.source_label_count,
        extraction.modeled_label_count,
    )
    if extraction.source_bytes != profile.source.expected_bytes:
        raise ValueError("GBmap preflight source byte length is outside the production lock")
    if observed_inventory != expected_inventory:
        raise ValueError("GBmap preflight inventory is outside the production recipe")
    expected_taxonomy = production_label_taxonomy().taxonomy_digest
    expected_reduction = production_reduction_recipe_digest()
    if (
        extraction.taxonomy_digest != expected_taxonomy
        or split.taxonomy_digest != expected_taxonomy
        or extraction.extraction_recipe_digest != expected_reduction
        or split.extraction_recipe_digest != expected_reduction
    ):
        raise ValueError("GBmap preflight production semantic digests do not reconcile")
    if (
        extraction.source_sha256 != split.source_file_sha256
        or extraction.source_bytes != split.source_bytes
    ):
        raise ValueError("GBmap preflight source identities do not reconcile")
    if (
        extraction.cell_level_material_retained
        or extraction.donor_identifiers_retained
        or extraction.donor_hashes_retained
        or extraction.donor_profiles_retained
        or extraction.aggregate_content_digest_retained
    ):
        raise ValueError("GBmap preflight extraction receipt is not deidentified")


def _validate_receipt_semantics(receipt: GbmapDevelopmentPreflightReceipt) -> None:
    profile = development_profile()
    split = receipt.validation_split_receipt.to_domain()
    _validate_production_receipts(receipt.extraction_receipt, split)
    if receipt.reviewed_sha256 != receipt.extraction_receipt.source_sha256:
        raise ValueError("GBmap preflight reviewed digest does not bind the extracted source")
    if (
        receipt.profile_id != profile.profile_id
        or receipt.profile_digest != profile.profile_digest
        or receipt.engine_semantic_digest != profile.engine_semantic_digest
    ):
        raise ValueError("GBmap preflight profile binding is not exact")
    expected_configuration_digest = training_configuration_digest()
    if receipt.training_configuration_digest != expected_configuration_digest:
        raise ValueError("GBmap preflight training configuration binding is not exact")
    expected_dimensions = _fold_dimensions(split)
    expected_summary = _task_summary(
        expected_dimensions,
        split,
        DEFAULT_TRAINING_CONFIGURATION,
    )
    if receipt.fold_dimensions != expected_dimensions or receipt.task_summary != expected_summary:
        raise ValueError("GBmap preflight task dimensions do not match the split receipt")
    expected_task_digest = _task_dimensions_digest(
        expected_dimensions,
        expected_summary,
        expected_configuration_digest,
    )
    if receipt.task_dimensions_digest != expected_task_digest:
        raise ValueError("GBmap preflight task-dimension digest does not verify")


def _build_receipt(
    extraction: GbmapExtractionResult,
    split_plan: ValidationSplitPlan,
    reviewed_sha256: Sha256Digest,
) -> GbmapDevelopmentPreflightReceipt:
    if type(extraction) is not GbmapExtractionResult or type(split_plan) is not ValidationSplitPlan:
        raise ValueError("GBmap preflight results are not exact internal types")
    split = split_plan.receipt
    _validate_production_receipts(extraction.receipt, split)
    if reviewed_sha256 != extraction.receipt.source_sha256:
        raise ValueError("GBmap preflight source digest differs from independent review")
    projected_split = _project_split(split)
    dimensions = _fold_dimensions(split)
    summary = _task_summary(dimensions, split, DEFAULT_TRAINING_CONFIGURATION)
    configuration_digest = training_configuration_digest()
    profile = development_profile()
    body: dict[str, object] = {
        "schema_version": OUTPUT_SCHEMA,
        "preflight_state": "structural_extraction_complete_training_not_run",
        "reviewed_sha256": reviewed_sha256,
        "profile_id": profile.profile_id,
        "profile_digest": profile.profile_digest,
        "engine_semantic_digest": profile.engine_semantic_digest,
        "training_configuration_digest": configuration_digest,
        "task_dimensions_digest": _task_dimensions_digest(
            dimensions,
            summary,
            configuration_digest,
        ),
        "extraction_receipt": extraction.receipt.model_dump(mode="json"),
        "validation_split_receipt": projected_split.model_dump(mode="json"),
        "fold_dimensions": [item.model_dump(mode="json") for item in dimensions],
        "task_summary": summary.model_dump(mode="json"),
        "source_admission_granted": False,
        "hierarchy_training_executed": False,
        "model_fitted": False,
        "model_parameters_retained": False,
        "production_artifact_permitted": False,
        "runtime_mount_permitted": False,
        "public_http_mounted": False,
        "public_cli_mounted": False,
        "source_path_retained": False,
        "cell_level_material_retained": False,
        "donor_identifiers_retained": False,
        "donor_hashes_retained": False,
        "donor_profiles_retained": False,
        "feature_identities_retained": False,
        "aggregate_content_digest_retained": False,
        "raw_material_retained": False,
    }
    validation_body = {
        **body,
        "extraction_receipt": extraction.receipt,
        "validation_split_receipt": projected_split,
        "fold_dimensions": dimensions,
        "task_summary": summary,
    }
    return GbmapDevelopmentPreflightReceipt.model_validate(
        {"receipt_digest": sha256_digest(body), **validation_body}
    )


def build_development_preflight_receipt(
    source: Path,
    reviewed_sha256: str,
    *,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> GbmapDevelopmentPreflightReceipt:
    """Extract and plan splits in memory, returning only deidentified evidence."""

    _require_acknowledgements(
        development_only_acknowledged=development_only_acknowledged,
        sha256_independently_reviewed=sha256_independently_reviewed,
    )
    reviewed_digest = _reviewed_sha256(reviewed_sha256)
    before = _capture_source_snapshot(source)
    guard = _open_source_guard(before)
    try:
        lock = _production_lock(reviewed_digest)
        dependencies = _privacy_call(
            "production GBmap preflight dependencies failed closed",
            lambda: (
                production_extraction_recipe(),
                production_donor_crosswalk(),
                production_study_crosswalk(),
                production_label_taxonomy(),
            ),
        )
        recipe, donor_crosswalk, study_crosswalk, taxonomy = dependencies
        extraction = _privacy_call(
            "GBmap preflight extraction failed closed",
            lambda: extract_pinned_gbmap_reference(
                source,
                lock=lock,
                taxonomy=taxonomy,
                donor_crosswalk=donor_crosswalk,
                study_crosswalk=study_crosswalk,
                recipe=recipe,
            ),
        )
        split_plan = _privacy_call(
            "GBmap preflight split planning failed closed",
            lambda: build_validation_split_plan(extraction.reference),
        )
        after = _capture_source_snapshot(source)
        _require_source_unchanged(before, after, guard)
        return _privacy_call(
            "GBmap preflight receipt projection failed closed",
            lambda: _build_receipt(extraction, split_plan, reviewed_digest),
        )
    finally:
        with suppress(OSError):
            guard.close()


def validate_preflight_json_bytes(payload: bytes) -> GbmapDevelopmentPreflightReceipt:
    """Parse and fully revalidate one canonical preflight receipt."""

    if type(payload) is not bytes or not payload or len(payload) > MAX_OUTPUT_BYTES:
        raise GbmapDevelopmentFitDriverError("GBmap preflight receipt bytes are invalid")
    receipt = _privacy_call(
        "GBmap preflight receipt failed strict validation",
        lambda: GbmapDevelopmentPreflightReceipt.model_validate_json(payload),
    )
    canonical = canonical_preflight_receipt_bytes(receipt)
    if payload != canonical:
        raise GbmapDevelopmentFitDriverError("GBmap preflight receipt is not canonical")
    return receipt


def canonical_preflight_receipt_bytes(receipt: GbmapDevelopmentPreflightReceipt) -> bytes:
    """Return bounded canonical JSON for an exact, fully validated receipt."""

    if type(receipt) is not GbmapDevelopmentPreflightReceipt:
        raise GbmapDevelopmentFitDriverError("GBmap preflight receipt type is not exact")
    encoded = canonical_json_bytes(receipt) + b"\n"
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise GbmapDevelopmentFitDriverError("GBmap preflight receipt exceeds the output bound")
    return encoded


def write_preflight_receipt(
    destination: Path,
    receipt: GbmapDevelopmentPreflightReceipt,
    *,
    source: Path,
) -> int:
    """Idempotently publish one verified receipt without replacing other bytes."""

    payload = canonical_preflight_receipt_bytes(receipt)
    _privacy_call(
        "GBmap preflight receipt publication failed closed",
        lambda: write_receipt(destination, payload, source=source),
    )
    return len(payload)


def run(
    source: Path,
    reviewed_sha256: str,
    destination: Path,
    *,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> GbmapDevelopmentPreflightReceipt:
    """Complete structural preflight and atomically publish its safe receipt."""

    receipt = build_development_preflight_receipt(
        source,
        reviewed_sha256,
        development_only_acknowledged=development_only_acknowledged,
        sha256_independently_reviewed=sha256_independently_reviewed,
    )
    write_preflight_receipt(destination, receipt, source=source)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="exact local scarches_core_GBmap.h5ad path")
    parser.add_argument(
        "--reviewed-sha256",
        required=True,
        help="independently reviewed canonical sha256:<64 lowercase hex> lock",
    )
    parser.add_argument("--output", required=True, type=Path, help="new private receipt JSON path")
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
        receipt = run(
            cast("Path", args.source),
            cast("str", args.reviewed_sha256),
            cast("Path", args.output),
            development_only_acknowledged=cast("bool", args.acknowledge_development_only),
            sha256_independently_reviewed=cast(
                "bool",
                args.acknowledge_sha256_independently_reviewed,
            ),
        )
        sys.stdout.write(canonical_preflight_receipt_bytes(receipt).decode("utf-8"))
    except (
        GbmapDevelopmentFitDriverError,
        GbmapDeconvolutionError,
        OSError,
        TypeError,
        ValueError,
    ):
        sys.stderr.write("error: GBmap structural preflight failed closed\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

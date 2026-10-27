"""Re-extract the admitted GBmap source and explain feature preparation without fitting."""

# ruff: noqa: TRY003 -- sanitize all private file-boundary failures

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from contextlib import suppress
from pathlib import Path
from typing import Final, Literal, Never, Self

from pydantic import Field, field_validator, model_validator

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.gbmap_deconvolution import (
    build_validation_split_plan,
    development_profile,
    extract_pinned_gbmap_reference,
    production_donor_crosswalk,
    production_extraction_recipe,
    production_label_taxonomy,
    production_study_crosswalk,
)
from glio_proteogen.research.gbmap_development_diagnostics import (
    ReferenceAttritionReceipt,
    audit_reference,
)
from glio_proteogen.research.gbmap_development_reduction import ValidationRunManifest
from tools import fit_gbmap_development_candidate as fit_driver
from tools import preflight_gbmap_development_candidate as preflight_driver
from tools import run_gbmap_hierarchy_tasks as tasks
from tools.capture_gbmap_source_admission import write_receipt

_ROOT: Final = Path(__file__).resolve().parents[1]
_MAX_BYTES: Final = 8 * 1024 * 1024


class AttritionAuditError(ValueError):
    """A sanitized source, preparation or publication binding failed."""


class SourceReplayBinding(FrozenModel):
    source_sha256: Sha256Digest
    source_bytes: int = Field(gt=0)
    taxonomy_digest: Sha256Digest
    extraction_recipe_digest: Sha256Digest
    feature_order_digest: Sha256Digest
    profile_id: Literal["gbmap-dm-composition/0.1.0-dev"]
    profile_digest: Sha256Digest
    engine_semantic_digest: Sha256Digest
    extraction_receipt_digest: Sha256Digest
    preflight_receipt_digest: Sha256Digest
    split_receipt_digest: Sha256Digest
    validation_fold_axis_digest: Sha256Digest


class ManifestPreparationComparison(FrozenModel):
    comparison_scope: Literal["preparation_counts_and_scheduled_lineage_axis_only"] = (
        "preparation_counts_and_scheduled_lineage_axis_only"
    )
    manifest_digest: Sha256Digest
    task_inventory_digest: Sha256Digest
    compared_fold_count: int = Field(ge=1)
    scheduled_task_count: int = Field(ge=0)
    hierarchy_results_inspected: Literal[False] = False
    training_matrix_replay_performed: Literal[False] = False

    @field_validator(
        "hierarchy_results_inspected", "training_matrix_replay_performed", mode="before"
    )
    @classmethod
    def false_is_exact(cls, value: object) -> object:
        if value is not False:
            raise ValueError("fixed false flags require exact false")
        return value


class DiagnosticBundle(FrozenModel):
    schema_version: Literal["glio-proteogen.gbmap-feature-attrition-bundle/1.0.0"] = (
        "glio-proteogen.gbmap-feature-attrition-bundle/1.0.0"
    )
    verification_kind: Literal["source_replayed_feature_preparation_diagnostics"] = (
        "source_replayed_feature_preparation_diagnostics"
    )
    method_digest: Sha256Digest
    source_replay: SourceReplayBinding
    report: ReferenceAttritionReceipt
    manifest_comparison: ManifestPreparationComparison | None
    bundle_digest: Sha256Digest

    @model_validator(mode="after")
    def bindings_are_consistent(self) -> Self:
        pairs = (
            (self.source_replay.source_sha256, self.report.source_file_sha256),
            (self.source_replay.source_bytes, self.report.source_bytes),
            (self.source_replay.taxonomy_digest, self.report.taxonomy_digest),
            (self.source_replay.extraction_recipe_digest, self.report.extraction_recipe_digest),
            (self.source_replay.feature_order_digest, self.report.feature_order_digest),
            (self.source_replay.profile_digest, self.report.development_profile_digest),
        )
        if any(left != right for left, right in pairs):
            raise AttritionAuditError("feature diagnostics source bindings differ")
        fold_axis = [
            [row.partition_id, row.kind]
            for row in self.report.partitions
            if row.kind != "full_source"
        ]
        if (
            self.report.planning_state != "completed"
            or self.source_replay.validation_fold_axis_digest != sha256_digest(fold_axis)
        ):
            raise AttritionAuditError("feature diagnostics fold axis does not reconcile")
        if self.manifest_comparison is not None:
            folds = tuple(row for row in self.report.partitions if row.kind != "full_source")
            scheduled = 0
            for row in folds:
                if row.preparation_state == "prepared":
                    if row.prepared_eligible_lineage_count is None:
                        raise AttritionAuditError("prepared diagnostics are missing dimensions")
                    scheduled += 4 * row.prepared_eligible_lineage_count
            if (
                self.manifest_comparison.compared_fold_count != len(folds)
                or self.manifest_comparison.scheduled_task_count != scheduled
            ):
                raise AttritionAuditError("manifest comparison dimensions do not reconcile")
        if self.bundle_digest != sha256_digest(
            self.model_dump(mode="json", exclude={"bundle_digest"})
        ):
            raise AttritionAuditError("feature diagnostics bundle seal differs")
        return self


def method_digest() -> str:
    sources: tuple[Path, ...] = ()
    for name in ("gbmap_development_diagnostics", "gbmap_development_reduction"):
        namespace = _ROOT / "src/glio_proteogen/research" / name
        members = tuple(sorted(namespace.glob("*.py")))
        if not members:
            raise AttritionAuditError("feature diagnostics method source is unavailable")
        sources += members
    sources += tuple(
        _ROOT / name
        for name in (
            "tools/audit_gbmap_feature_attrition.py",
            "tools/fit_gbmap_development_candidate.py",
            "tools/preflight_gbmap_development_candidate.py",
            "tools/run_gbmap_hierarchy_tasks.py",
            "tools/capture_gbmap_source_admission.py",
        )
    )
    return sha256_digest(
        {
            "development_profile_digest": development_profile().profile_digest,
            "source_bindings": {
                path.relative_to(_ROOT).as_posix(): "sha256:"
                + hashlib.sha256(
                    tasks._read_regular_bytes(
                        path, _MAX_BYTES, "feature diagnostics method could not be read"
                    ).replace(b"\r\n", b"\n")
                ).hexdigest()
                for path in sources
            },
        }
    )


def _manifest_snapshot(
    run_directory: Path,
) -> tuple[Path, bytes, ValidationRunManifest]:
    if not run_directory.is_dir():
        raise AttritionAuditError("an existing private hierarchy directory is required")
    directory = tasks._inspect_private_directory(run_directory)
    payload = tasks._read_regular_bytes(
        directory / tasks.MANIFEST_NAME,
        tasks.MAX_MANIFEST_BYTES,
        "the existing hierarchy manifest could not be read",
    )
    original = tasks.validate_manifest_json_bytes(payload)
    manifest = ValidationRunManifest.model_validate(original.model_dump(mode="python"))
    return directory, payload, manifest


def _require_manifest_context(
    manifest: ValidationRunManifest,
    preflight: preflight_driver.GbmapDevelopmentPreflightReceipt,
) -> None:
    expected = {
        "reviewed_sha256": preflight.reviewed_sha256,
        "source_bytes": preflight.extraction_receipt.source_bytes,
        "taxonomy_digest": preflight.extraction_receipt.taxonomy_digest,
        "extraction_recipe_digest": preflight.extraction_receipt.extraction_recipe_digest,
        "extraction_receipt_digest": preflight.extraction_receipt.receipt_digest,
        "preflight_receipt_digest": preflight.receipt_digest,
        "preflight_task_dimensions_digest": preflight.task_dimensions_digest,
        "profile_id": preflight.profile_id,
        "profile_digest": preflight.profile_digest,
        "engine_semantic_digest": preflight.engine_semantic_digest,
        "training_configuration_digest": preflight.training_configuration_digest,
        "split_receipt_digest": sha256_digest(
            preflight.validation_split_receipt.model_dump(mode="json")
        ),
        "feature_order_digest": preflight.extraction_receipt.feature_order_digest,
    }
    document = manifest.model_dump(mode="python")
    if any(document[name] != value for name, value in expected.items()):
        raise AttritionAuditError("hierarchy context differs from the approved preflight")


def _compare_preparation(
    report: ReferenceAttritionReceipt, manifest: ValidationRunManifest
) -> ManifestPreparationComparison:
    partitions = {row.partition_id: row for row in report.partitions if row.kind != "full_source"}
    if set(partitions) != {row.fold_id for row in manifest.preparation_receipts}:
        raise AttritionAuditError("diagnostic and hierarchy fold inventories differ")
    for prepared in manifest.preparation_receipts:
        observed = partitions[prepared.fold_id]
        if (
            observed.preparation_state != prepared.state
            or observed.preparation_reason != prepared.abstention_reason
            or observed.prepared_eligible_lineage_count != prepared.eligible_lineage_count
            or observed.prepared_feature_count != prepared.selected_feature_count
        ):
            raise AttritionAuditError("diagnostics disagree with original fold preparation")
        scheduled_labels = {
            row.modeled_label for row in manifest.tasks if row.fold_id == prepared.fold_id
        }
        observed_labels = {row.modeled_label for row in observed.labels if row.enters_prepared_fold}
        if observed_labels != scheduled_labels:
            raise AttritionAuditError("diagnostics disagree with scheduled lineage labels")
    return ManifestPreparationComparison(
        manifest_digest=manifest.manifest_digest,
        task_inventory_digest=manifest.task_inventory_digest,
        compared_fold_count=len(partitions),
        scheduled_task_count=manifest.task_count,
    )


def _require_report_fold_axis(
    report: ReferenceAttritionReceipt,
    preflight: preflight_driver.GbmapDevelopmentPreflightReceipt,
) -> None:
    expected = tuple((row.fold_id, row.kind) for row in preflight.validation_split_receipt.folds)
    observed = tuple(
        (row.partition_id, row.kind) for row in report.partitions if row.kind != "full_source"
    )
    if report.planning_state != "completed" or observed != expected:
        raise AttritionAuditError("diagnostics differ from the original validation fold axis")


def _bundle(
    preflight: preflight_driver.GbmapDevelopmentPreflightReceipt,
    report: ReferenceAttritionReceipt,
    comparison: ManifestPreparationComparison | None,
) -> DiagnosticBundle:
    replay = SourceReplayBinding(
        source_sha256=preflight.reviewed_sha256,
        source_bytes=preflight.extraction_receipt.source_bytes,
        taxonomy_digest=preflight.extraction_receipt.taxonomy_digest,
        extraction_recipe_digest=preflight.extraction_receipt.extraction_recipe_digest,
        feature_order_digest=preflight.extraction_receipt.feature_order_digest,
        profile_id=preflight.profile_id,
        profile_digest=preflight.profile_digest,
        engine_semantic_digest=preflight.engine_semantic_digest,
        extraction_receipt_digest=preflight.extraction_receipt.receipt_digest,
        preflight_receipt_digest=preflight.receipt_digest,
        split_receipt_digest=sha256_digest(
            preflight.validation_split_receipt.model_dump(mode="json")
        ),
        validation_fold_axis_digest=sha256_digest(
            [[row.fold_id, row.kind] for row in preflight.validation_split_receipt.folds]
        ),
    )
    materialized = DiagnosticBundle.model_construct(
        method_digest=method_digest(),
        source_replay=replay,
        report=report,
        manifest_comparison=comparison,
        bundle_digest="sha256:" + "0" * 64,
    ).model_dump(mode="json", exclude={"bundle_digest"})
    return DiagnosticBundle.model_validate_json(
        canonical_json_bytes({**materialized, "bundle_digest": sha256_digest(materialized)})
    )


def run_audit(  # noqa: PLR0913
    source: Path,
    reviewed_sha256: str,
    preflight_path: Path,
    *,
    run_directory: Path | None = None,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> DiagnosticBundle:
    """Read the exact source once, explain preparation, and retain aggregate diagnostics only."""
    fit_driver._require_acknowledgements(
        development_only_acknowledged=development_only_acknowledged,
        sha256_independently_reviewed=sha256_independently_reviewed,
    )
    reviewed = fit_driver._reviewed_sha256(reviewed_sha256)
    payload = tasks._read_regular_bytes(
        preflight_path, tasks.MAX_PREFLIGHT_BYTES, "the structural preflight could not be read"
    )
    preflight = preflight_driver.validate_preflight_json_bytes(payload)
    if preflight.reviewed_sha256 != reviewed:
        raise AttritionAuditError("the preflight does not bind the independently reviewed source")
    snapshot = None if run_directory is None else _manifest_snapshot(run_directory)
    if snapshot is not None:
        _require_manifest_context(snapshot[2], preflight)
    before = fit_driver._capture_source_snapshot(source)
    if snapshot is not None and fit_driver._is_within(before.lexical_path, snapshot[0]):
        raise AttritionAuditError("the source must remain outside its hierarchy run")
    guard = fit_driver._open_source_guard(before)
    try:
        extraction = extract_pinned_gbmap_reference(
            source,
            lock=fit_driver._production_lock(reviewed),
            taxonomy=production_label_taxonomy(),
            donor_crosswalk=production_donor_crosswalk(),
            study_crosswalk=production_study_crosswalk(),
            recipe=production_extraction_recipe(),
        )
        plan = build_validation_split_plan(extraction.reference)
        if preflight_driver._build_receipt(extraction, plan, reviewed) != preflight:
            raise AttritionAuditError("source replay differs from the approved preflight")
        report = audit_reference(
            extraction.reference, development_profile_digest=preflight.profile_digest
        )
        _require_report_fold_axis(report, preflight)
        comparison = None if snapshot is None else _compare_preparation(report, snapshot[2])
        bundle = _bundle(preflight, report, comparison)
        if snapshot is not None and _manifest_snapshot(snapshot[0]) != snapshot:
            raise AttritionAuditError("the hierarchy manifest changed during feature diagnostics")
        fit_driver._require_source_unchanged(
            before, fit_driver._capture_source_snapshot(source), guard
        )
        return bundle
    finally:
        with suppress(OSError):
            guard.close()


def canonical_bundle_bytes(bundle: DiagnosticBundle) -> bytes:
    checked = DiagnosticBundle.model_validate(bundle.model_dump(mode="python"))
    payload = canonical_json_bytes(checked.model_dump(mode="json")) + b"\n"
    if len(payload) > _MAX_BYTES:
        raise AttritionAuditError("feature diagnostics exceed the retained output bound")
    return payload


def verify_saved(path: Path) -> dict[str, object]:
    payload = tasks._read_regular_bytes(
        path, _MAX_BYTES, "saved feature diagnostics are unavailable"
    )
    bundle = DiagnosticBundle.model_validate_json(payload)
    profile = development_profile()
    if (
        payload != canonical_bundle_bytes(bundle)
        or bundle.method_digest != method_digest()
        or bundle.source_replay.profile_digest != profile.profile_digest
        or bundle.source_replay.engine_semantic_digest != profile.engine_semantic_digest
    ):
        raise AttritionAuditError(
            "saved feature diagnostics differ from the canonical current method"
        )
    return {
        "verified": True,
        "verification_scope": "saved_integrity_not_source_replay",
        "bundle_digest": bundle.bundle_digest,
        "hierarchy_training_executed": False,
        "model_fitted": False,
        "runtime_mount_permitted": False,
    }


def _publish(
    destination: Path, payload: bytes, *, source: Path, run_directory: Path | None
) -> None:
    lexical = fit_driver._lexical_absolute(destination)
    if run_directory is not None:
        directory, _, _ = _manifest_snapshot(run_directory)
        if lexical.is_relative_to(directory):
            raise AttritionAuditError("diagnostics output must remain outside the hierarchy run")
    parent = tasks._inspect_private_directory(lexical.parent)
    write_receipt(parent / lexical.name, payload, source=source)


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> Never:
        sys.stderr.write("error: feature diagnostics arguments were not accepted\n")
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("source", type=Path)
    run.add_argument("--reviewed-sha256", required=True)
    run.add_argument("--preflight", type=Path, required=True)
    run.add_argument("--run-directory", type=Path)
    run.add_argument("--output", type=Path)
    run.add_argument("--acknowledge-development-only", action="store_true", required=True)
    run.add_argument(
        "--acknowledge-sha256-independently-reviewed", action="store_true", required=True
    )
    verify = commands.add_parser("verify")
    verify.add_argument("receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            sys.stdout.write(json.dumps(verify_saved(args.receipt), sort_keys=True) + "\n")
            return 0
        bundle = run_audit(
            args.source,
            args.reviewed_sha256,
            args.preflight,
            run_directory=args.run_directory,
            development_only_acknowledged=args.acknowledge_development_only,
            sha256_independently_reviewed=args.acknowledge_sha256_independently_reviewed,
        )
        payload = canonical_bundle_bytes(bundle)
        if args.output is not None:
            _publish(args.output, payload, source=args.source, run_directory=args.run_directory)
        sys.stdout.write(payload.decode())
    except Exception:  # noqa: BLE001 -- never echo private source paths or data-bearing exceptions
        sys.stderr.write("error: GBmap feature diagnostics failed closed\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

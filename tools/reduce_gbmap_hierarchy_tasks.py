"""Assess or reduce complete private GBmap validation tasks without publishing a model."""

# ruff: noqa: TRY003 -- stable sanitized errors at the private file boundary

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from contextlib import suppress
from pathlib import Path
from typing import Literal, Never, Self

from pydantic import model_validator

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.gbmap_deconvolution import development_profile
from glio_proteogen.research.gbmap_development_reduction import (
    CandidateSelectionReceipt,
    PlanningFeasibilityReceipt,
    ReductionError,
    ValidationCheckpoint,
    ValidationRunManifest,
    assess_manifest_feasibility,
    reduce_completed_validation,
)
from tools import fit_gbmap_development_candidate as fit_driver
from tools import run_gbmap_hierarchy_tasks as tasks
from tools.capture_gbmap_source_admission import write_receipt

_ROOT = Path(__file__).resolve().parents[1]
_MAX_BYTES = 4 * 1024 * 1024


class ReductionBundle(FrozenModel):
    schema_version: Literal["glio-proteogen.gbmap-validation-reduction/1.0.0"] = (
        "glio-proteogen.gbmap-validation-reduction/1.0.0"
    )
    verification_kind: Literal["saved_plan_feasibility", "source_replayed_complete_task_reduction"]
    method_digest: Sha256Digest
    planning: PlanningFeasibilityReceipt
    selection: CandidateSelectionReceipt | None
    source_replay_receipt_digest: Sha256Digest | None
    bundle_digest: Sha256Digest

    @model_validator(mode="after")
    def bindings_are_consistent(self) -> Self:
        complete = self.verification_kind == "source_replayed_complete_task_reduction"
        if complete != (self.selection is not None) or complete != (
            self.source_replay_receipt_digest is not None
        ):
            raise ReductionError("validation reduction scope does not match its evidence")
        if self.selection is not None and (
            self.selection.manifest_digest != self.planning.manifest_digest
            or self.selection.task_inventory_digest != self.planning.task_inventory_digest
        ):
            raise ReductionError("validation reduction inventories do not match")
        if self.bundle_digest != sha256_digest(
            self.model_dump(mode="json", exclude={"bundle_digest"})
        ):
            raise ReductionError("validation reduction bundle seal differs")
        return self


def method_digest() -> str:
    names = (
        "src/glio_proteogen/research/gbmap_development_reduction/__init__.py",
        "src/glio_proteogen/research/gbmap_development_reduction/contracts.py",
        "src/glio_proteogen/research/gbmap_development_reduction/reduction.py",
        "tools/run_gbmap_hierarchy_tasks.py",
        "tools/reduce_gbmap_hierarchy_tasks.py",
    )
    return sha256_digest(
        {
            "development_profile_digest": development_profile().profile_digest,
            "source_bindings": {
                name: "sha256:"
                + hashlib.sha256(
                    tasks._read_regular_bytes(
                        _ROOT / name,
                        tasks.MAX_MANIFEST_BYTES,
                        "validation reduction method could not be read",
                    ).replace(b"\r\n", b"\n")
                ).hexdigest()
                for name in names
            },
        }
    )


def _manifest(run_directory: Path) -> tuple[Path, tasks.GbmapHierarchyRunManifest]:
    if not run_directory.is_dir():
        raise ReductionError("an existing private hierarchy run is required")
    directory = tasks._inspect_private_directory(run_directory)
    manifest = tasks._load_manifest_if_present(directory)
    if manifest is None:
        raise ReductionError("the hierarchy run manifest is missing")
    return directory, manifest


def _bundle(
    manifest: tasks.GbmapHierarchyRunManifest,
    selection: CandidateSelectionReceipt | None,
    replay_digest: str | None,
) -> ReductionBundle:
    planning = assess_manifest_feasibility(
        ValidationRunManifest.model_validate(manifest.model_dump(mode="python"))
    )
    provisional = ReductionBundle.model_construct(
        verification_kind="saved_plan_feasibility"
        if selection is None
        else "source_replayed_complete_task_reduction",
        method_digest=method_digest(),
        planning=planning,
        selection=selection,
        source_replay_receipt_digest=replay_digest,
        bundle_digest="sha256:" + "0" * 64,
    ).model_dump(mode="json")
    provisional.pop("bundle_digest")
    return ReductionBundle.model_validate_json(
        canonical_json_bytes({**provisional, "bundle_digest": sha256_digest(provisional)})
    )


def assess_run(run_directory: Path) -> ReductionBundle:
    """Read the sealed saved plan only; do not inspect the H5AD or fit tasks."""
    _, manifest = _manifest(run_directory)
    return _bundle(manifest, None, None)


def reduce_run(  # noqa: PLR0913
    source: Path,
    reviewed_sha256: str,
    preflight_path: Path,
    run_directory: Path,
    *,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> ReductionBundle:
    """Re-extract and reconcile all private bindings before complete-task reduction."""
    directory, before_manifest = _manifest(run_directory)
    before_checkpoints = tasks._load_checkpoints(directory, before_manifest, None)
    if len(before_checkpoints) != before_manifest.task_count:
        raise ReductionError("the exact hierarchy task inventory is incomplete")
    before = fit_driver._capture_source_snapshot(source)
    guard = fit_driver._open_source_guard(before)
    try:
        replay = tasks.run_batch(
            source,
            reviewed_sha256,
            preflight_path,
            directory,
            max_tasks=1,
            dry_run=True,
            development_only_acknowledged=development_only_acknowledged,
            sha256_independently_reviewed=sha256_independently_reviewed,
        )
        _, manifest = _manifest(directory)
        if manifest != before_manifest or replay.manifest_digest != manifest.manifest_digest:
            raise ReductionError("hierarchy run changed during source reconciliation")
        checkpoints = tasks._load_checkpoints(directory, manifest, None)
        if len(checkpoints) != manifest.task_count or not replay.run_complete:
            raise ReductionError("the exact hierarchy task inventory is incomplete")
        if before_checkpoints != checkpoints:
            raise ReductionError("hierarchy checkpoints changed during source reconciliation")
        selection = reduce_completed_validation(
            ValidationRunManifest.model_validate(manifest.model_dump(mode="python")),
            tuple(
                ValidationCheckpoint.model_validate(row.model_dump(mode="python"))
                for _, row in sorted(checkpoints.items())
            ),
        )
        _, final_manifest = _manifest(directory)
        if (
            final_manifest != manifest
            or tasks._load_checkpoints(directory, manifest, None) != checkpoints
        ):
            raise ReductionError("hierarchy state changed during complete-task reduction")
        fit_driver._require_source_unchanged(
            before, fit_driver._capture_source_snapshot(source), guard
        )
        return _bundle(manifest, selection, replay.receipt_digest)
    finally:
        with suppress(OSError):
            guard.close()


def canonical_bundle_bytes(bundle: ReductionBundle) -> bytes:
    checked = ReductionBundle.model_validate(bundle.model_dump(mode="python"))
    payload = canonical_json_bytes(checked.model_dump(mode="json")) + b"\n"
    if len(payload) > _MAX_BYTES:
        raise ReductionError("validation reduction exceeds its output bound")
    return payload


def verify_saved(path: Path) -> dict[str, object]:
    payload = tasks._read_regular_bytes(
        path, _MAX_BYTES, "saved validation reduction could not be read"
    )
    bundle = ReductionBundle.model_validate_json(payload)
    if payload != canonical_bundle_bytes(bundle) or bundle.method_digest != method_digest():
        raise ReductionError("saved validation reduction differs from its canonical method")
    return {
        "verified": True,
        "verification_scope": "saved_integrity_not_source_replay",
        "bundle_digest": bundle.bundle_digest,
        "model_fitted": False,
        "model_artifact_emitted": False,
        "runtime_mount_permitted": False,
    }


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> Never:
        sys.stderr.write("error: validation reduction arguments were not accepted\n")
        raise SystemExit(2)


def _publish(destination: Path, run_directory: Path, payload: bytes) -> None:
    parent = tasks._inspect_private_directory(destination.parent)
    destination = parent / destination.name
    directory, _ = _manifest(run_directory)
    if destination.is_relative_to(directory):
        raise ReductionError("validation output must remain outside the hierarchy run")
    write_receipt(destination, payload, source=directory / tasks.MANIFEST_NAME)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    assess = commands.add_parser("assess")
    assess.add_argument("run_directory", type=Path)
    reduce = commands.add_parser("reduce")
    reduce.add_argument("run_directory", type=Path)
    reduce.add_argument("--source", type=Path, required=True)
    reduce.add_argument("--reviewed-sha256", required=True)
    reduce.add_argument("--preflight", type=Path, required=True)
    reduce.add_argument("--acknowledge-development-only", required=True, action="store_true")
    reduce.add_argument(
        "--acknowledge-sha256-independently-reviewed", required=True, action="store_true"
    )
    for command in (assess, reduce):
        command.add_argument("--output", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            sys.stdout.write(json.dumps(verify_saved(args.receipt), sort_keys=True) + "\n")
            return 0
        bundle = (
            assess_run(args.run_directory)
            if args.command == "assess"
            else reduce_run(
                args.source,
                args.reviewed_sha256,
                args.preflight,
                args.run_directory,
                development_only_acknowledged=args.acknowledge_development_only,
                sha256_independently_reviewed=args.acknowledge_sha256_independently_reviewed,
            )
        )
        payload = canonical_bundle_bytes(bundle)
        if args.output is not None:
            _publish(args.output, args.run_directory, payload)
        sys.stdout.write(payload.decode())
    except Exception:  # noqa: BLE001 -- sanitize private paths and data-bearing nested failures
        sys.stderr.write("error: GBmap validation reduction failed closed\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Recover one private selected-fold context by exact checkpoint reproduction.

The source is extracted once through the existing guarded extractor. Every
saved task is reconciled before complete reduction; only the selected fold's
lineages are refitted. The command prints an aggregate receipt, never reusable
parameters, raw held cases, a fitted artifact or a production admission.
"""

# ruff: noqa: TRY003 -- stable sanitized errors at the private boundary

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from contextlib import suppress
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Never

import numpy as np
import numpy.typing as npt

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.gbmap_deconvolution import (
    DEFAULT_TRAINING_CONFIGURATION,
    build_validation_split_plan,
    extract_pinned_gbmap_reference,
    production_donor_crosswalk,
    production_extraction_recipe,
    production_label_taxonomy,
    production_study_crosswalk,
    verify_hierarchy_trace,
)
from glio_proteogen.research.gbmap_deconvolution.training import _fit_label, _PreparedFold
from glio_proteogen.research.gbmap_development_reduction import (
    CandidateSelectionReceipt,
    ValidationCheckpoint,
    ValidationRunManifest,
    reduce_completed_validation,
)
from glio_proteogen.research.gbmap_held_mixture_truth import (
    CallerOwnedMixtureContext,
    build_held_mixture_truth,
)
from glio_proteogen.research.gbmap_selected_fold_replay import (
    SelectedFoldReplayError,
    SelectedFoldReplayReceipt,
    SelectedFoldReplayResult,
)
from glio_proteogen.research.gbmap_selected_fold_replay.model import _build_result
from glio_proteogen.research.proteogenomic_state.cancellation import InferenceCancelledError
from tools import fit_gbmap_development_candidate as fit_driver
from tools import preflight_gbmap_development_candidate as preflight_driver
from tools import run_gbmap_hierarchy_tasks as tasks

_FOLD_PATTERN = re.compile(r"^(?:whole-study|within-study-donor)-[0-9]{4}$")
_MAX_RECEIPT_BYTES = 128 * 1024


@dataclass(frozen=True, slots=True, repr=False)
class _RunSnapshot:
    directory: Path
    directory_identities: tuple[tuple[Path, tuple[int, ...]], ...]
    checkpoint_directory_identities: tuple[tuple[Path, tuple[int, ...]], ...]
    manifest: tasks.GbmapHierarchyRunManifest
    checkpoints: tuple[tuple[str, tasks.GbmapHierarchyCheckpoint], ...]


def _existing_private_directory(
    path: Path,
) -> tuple[Path, tuple[tuple[Path, tuple[int, ...]], ...]]:
    if not isinstance(path, Path):
        raise SelectedFoldReplayError("an existing private directory is required")
    lexical = fit_driver._lexical_absolute(path)
    if fit_driver._is_within(lexical, fit_driver._REPOSITORY_ROOT):
        raise SelectedFoldReplayError("the hierarchy run must remain outside the repository")
    identities = []
    for ancestor in reversed((lexical, *lexical.parents)):
        info = ancestor.lstat()
        if fit_driver._is_link_or_reparse(info) or not stat.S_ISDIR(info.st_mode):
            raise SelectedFoldReplayError("private directory ancestors must be ordinary")
        identities.append((ancestor, fit_driver._ancestor_identity(info)))
    for ancestor, expected in identities:
        if fit_driver._ancestor_identity(ancestor.lstat()) != expected:
            raise SelectedFoldReplayError("private directory ancestors changed during inspection")
    return lexical, tuple(identities)


def _read_checkpoints(
    directory: Path,
    manifest: tasks.GbmapHierarchyRunManifest,
    runtime_by_digest: dict[str, tasks._RuntimeTask] | None,
) -> dict[str, tasks.GbmapHierarchyCheckpoint]:
    """Read an existing inventory without the old loader's mkdir preparation."""
    specs = {task.task_digest: task for task in manifest.tasks}
    retained = {}
    with os.scandir(directory) as listing:
        entries = tuple(Path(entry.path) for entry in islice(listing, manifest.task_count + 1))
    if len(entries) > manifest.task_count:
        raise SelectedFoldReplayError("the checkpoint inventory exceeds the exact task count")
    for path in sorted(entries, key=lambda item: item.name):
        if tasks._CHECKPOINT_NAME_PATTERN.fullmatch(path.name) is None:
            raise SelectedFoldReplayError("the checkpoint inventory contains an unexpected entry")
        checkpoint = tasks.validate_checkpoint_json_bytes(
            tasks._read_regular_bytes(
                path, tasks.MAX_CHECKPOINT_BYTES, "a hierarchy checkpoint is unavailable"
            )
        )
        if path.name != tasks._checkpoint_filename(checkpoint):
            raise SelectedFoldReplayError("a checkpoint filename is not content-addressed")
        spec = specs.get(checkpoint.task_digest)
        if spec is None or checkpoint.task_digest in retained:
            raise SelectedFoldReplayError("the checkpoint task inventory is invalid")
        runtime = (
            None if runtime_by_digest is None else runtime_by_digest.get(checkpoint.task_digest)
        )
        if runtime_by_digest is not None and runtime is None:
            raise SelectedFoldReplayError("a checkpoint has no reconstructed runtime")
        tasks._validate_checkpoint_binding(checkpoint, manifest, spec, runtime)
        retained[checkpoint.task_digest] = checkpoint
    return retained


def _snapshot_run(
    run_directory: Path,
    runtime_by_digest: dict[str, tasks._RuntimeTask] | None = None,
) -> _RunSnapshot:
    directory, directory_identities = _existing_private_directory(run_directory)
    checkpoint_directory, checkpoint_identities = _existing_private_directory(
        directory / tasks.CHECKPOINT_DIRECTORY_NAME
    )
    manifest = tasks._load_manifest_if_present(directory)
    if manifest is None:
        raise SelectedFoldReplayError("the hierarchy run manifest is missing")
    checkpoints = _read_checkpoints(checkpoint_directory, manifest, runtime_by_digest)
    if len(checkpoints) != manifest.task_count:
        raise SelectedFoldReplayError("the exact hierarchy checkpoint inventory is incomplete")
    if (
        _existing_private_directory(directory)[1] != directory_identities
        or _existing_private_directory(checkpoint_directory)[1] != checkpoint_identities
    ):
        raise SelectedFoldReplayError("the hierarchy run directory changed during inspection")
    return _RunSnapshot(
        directory,
        directory_identities,
        checkpoint_identities,
        manifest,
        tuple(sorted(checkpoints.items())),
    )


def _require_run_unchanged(
    snapshot: _RunSnapshot,
    runtime_by_digest: dict[str, tasks._RuntimeTask],
) -> None:
    if _snapshot_run(snapshot.directory, runtime_by_digest) != snapshot:
        raise SelectedFoldReplayError("the hierarchy run changed during selected-fold replay")


def _complete_selection(snapshot: _RunSnapshot) -> CandidateSelectionReceipt:
    return reduce_completed_validation(
        ValidationRunManifest.model_validate(snapshot.manifest.model_dump(mode="python")),
        tuple(
            ValidationCheckpoint.model_validate(row.model_dump(mode="python"))
            for _, row in snapshot.checkpoints
        ),
    )


def _selected_runtime(
    selection: CandidateSelectionReceipt,
    runtime: tuple[tasks._RuntimeTask, ...],
    fold_id: str,
) -> tuple[_PreparedFold, tuple[tasks._RuntimeTask, ...]]:
    index = selection.selected_shrinkage_index
    shrinkage = selection.selected_shrinkage
    if index is None or shrinkage is None:
        raise SelectedFoldReplayError("complete reduction did not select a candidate")
    candidate = selection.candidates[index]
    folds = tuple(fold for fold in candidate.folds if fold.fold_id == fold_id)
    if len(folds) != 1 or folds[0].state != "evaluated":
        raise SelectedFoldReplayError("the requested selected fold was not evaluated")
    selected = tuple(
        task
        for task in runtime
        if task.spec.fold_id == fold_id and task.spec.shrinkage_index == index
    )
    if not selected:
        raise SelectedFoldReplayError("the selected fold has no reconstructed runtime")
    prepared = selected[0].prepared
    if (
        type(prepared) is not _PreparedFold
        or any(task.prepared is not prepared for task in selected)
        or tuple(task.spec.modeled_label for task in selected) != prepared.labels
        or len(selected) != folds[0].eligible_lineage_count
        or any(task.spec.shrinkage != shrinkage for task in selected)
    ):
        raise SelectedFoldReplayError("the selected fold axes do not match their runtime")
    return prepared, selected


def _reproduce_checkpoint(
    manifest: tasks.GbmapHierarchyRunManifest,
    task: tasks._RuntimeTask,
    checkpoint: tasks.GbmapHierarchyCheckpoint,
) -> tuple[npt.NDArray[np.float64], float]:
    tasks._validate_checkpoint_binding(checkpoint, manifest, task.spec, task)
    if checkpoint.evaluation.state != "evaluated":
        raise SelectedFoldReplayError("a selected lineage checkpoint was not evaluated")
    fit = _fit_label(
        task.prepared.training_records,
        reference=task.prepared.reference,
        label=task.spec.modeled_label,
        feature_indices=task.prepared.feature_indices,
        background=task.prepared.background,
        shrinkage=task.spec.shrinkage,
        configuration=DEFAULT_TRAINING_CONFIGURATION.hierarchy,
        cancellation=None,
    )
    if not fit.converged or not verify_hierarchy_trace(fit):
        raise SelectedFoldReplayError("a selected lineage refit did not verify")
    if (
        tasks._fit_semantic_digest(fit) != checkpoint.evaluation.hierarchy_fit_digest
        or tasks._trace_digest(fit) != checkpoint.evaluation.hierarchy_trace_digest
    ):
        raise SelectedFoldReplayError("a selected lineage refit differs from its checkpoint")
    held = tasks._held_score(task, fit)
    if held is None:
        raise SelectedFoldReplayError("a selected lineage refit has no held evaluation")
    held_records, held_studies, score = held
    evaluation = tasks._evaluation_output(
        state="evaluated",
        reason=None,
        fit=fit,
        held_record_count=held_records,
        held_study_count=held_studies,
        mean_per_count_nll=score,
    )
    body = tasks._checkpoint_body(manifest, task.spec, evaluation)
    reproduced = tasks.GbmapHierarchyCheckpoint.model_validate(
        {"checkpoint_digest": sha256_digest(body), **body, "evaluation": evaluation}
    )
    if reproduced != checkpoint:
        raise SelectedFoldReplayError("a selected lineage evaluation differs from its checkpoint")
    return np.array(fit.global_signature, dtype=np.float64, copy=True), fit.concentration


def _recover_selected_fold_context(  # noqa: PLR0913 -- one guarded private scope
    source: Path,
    reviewed_sha256: str,
    preflight_path: Path,
    run_directory: Path,
    *,
    fold_id: str,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> SelectedFoldReplayResult:
    fit_driver._require_acknowledgements(
        development_only_acknowledged=development_only_acknowledged,
        sha256_independently_reviewed=sha256_independently_reviewed,
    )
    reviewed = fit_driver._reviewed_sha256(reviewed_sha256)
    if type(fold_id) is not str or _FOLD_PATTERN.fullmatch(fold_id) is None:
        raise SelectedFoldReplayError("an exact original fold identifier is required")
    payload = tasks._read_regular_bytes(
        preflight_path, tasks.MAX_PREFLIGHT_BYTES, "the structural preflight is unavailable"
    )
    preflight = preflight_driver.validate_preflight_json_bytes(payload)
    if preflight.reviewed_sha256 != reviewed:
        raise SelectedFoldReplayError("the preflight does not bind the reviewed source")
    snapshot = _snapshot_run(run_directory)
    before = fit_driver._capture_source_snapshot(source)
    if fit_driver._is_within(before.lexical_path, snapshot.directory):
        raise SelectedFoldReplayError("the source must remain outside the hierarchy run")
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
        manifest, runtime = tasks._build_manifest_and_tasks(extraction, plan, preflight)
        if manifest != snapshot.manifest:
            raise SelectedFoldReplayError("the hierarchy manifest differs from source replay")
        runtime_by_digest = {task.spec.task_digest: task for task in runtime}
        _require_run_unchanged(snapshot, runtime_by_digest)
        selection = _complete_selection(snapshot)
        prepared, selected = _selected_runtime(selection, runtime, fold_id)
        fit_driver._require_source_unchanged(
            before, fit_driver._capture_source_snapshot(source), guard
        )
        _require_run_unchanged(snapshot, runtime_by_digest)
        checkpoints = dict(snapshot.checkpoints)
        reproduced = tuple(
            _reproduce_checkpoint(manifest, task, checkpoints[task.spec.task_digest])
            for task in selected
        )
        fit_driver._require_source_unchanged(
            before, fit_driver._capture_source_snapshot(source), guard
        )
        _require_run_unchanged(snapshot, runtime_by_digest)
        held_truth = build_held_mixture_truth(
            extraction.reference,
            plan,
            fold_id=fold_id,
            context=CallerOwnedMixtureContext(
                feature_indices=prepared.feature_indices,
                known_labels=prepared.labels,
                feature_order_digest=manifest.feature_order_digest,
            ),
        )
        receipt = SelectedFoldReplayReceipt(
            fold_id=fold_id,
            kind=prepared.fold.kind,
            selected_shrinkage_index=selected[0].spec.shrinkage_index,
            selected_shrinkage=selected[0].spec.shrinkage,
            selected_feature_count=len(prepared.feature_indices),
            known_labels=prepared.labels,
            manifest_digest=manifest.manifest_digest,
            selection_receipt_digest=selection.receipt_digest,
            checkpoint_set_digest=selection.checkpoint_set_digest,
            reviewed_sha256=manifest.reviewed_sha256,
            profile_digest=manifest.profile_digest,
            engine_semantic_digest=manifest.engine_semantic_digest,
            training_configuration_digest=manifest.training_configuration_digest,
            feature_order_digest=manifest.feature_order_digest,
            selected_feature_axis_digest=selected[0].spec.selected_feature_axis_digest,
            replayed_checkpoint_count=len(selected),
            held_truth=held_truth.receipt,
        )
        result = _build_result(
            receipt=receipt,
            feature_indices=prepared.feature_indices,
            signatures=np.column_stack(tuple(value[0] for value in reproduced)),
            background=prepared.background,
            hierarchy_concentrations=tuple(value[1] for value in reproduced),
            held_truth=held_truth,
        )
        fit_driver._require_source_unchanged(
            before, fit_driver._capture_source_snapshot(source), guard
        )
        _require_run_unchanged(snapshot, runtime_by_digest)
        return result
    finally:
        with suppress(OSError):
            guard.close()


def recover_selected_fold_context(  # noqa: PLR0913 -- exact offline producer interface
    source: Path,
    reviewed_sha256: str,
    preflight_path: Path,
    run_directory: Path,
    *,
    fold_id: str,
    development_only_acknowledged: bool,
    sha256_independently_reviewed: bool,
) -> SelectedFoldReplayResult:
    """Reproduce selected checkpoints before returning private parameters and truth."""
    result: SelectedFoldReplayResult | None = None
    failed = False
    try:
        result = _recover_selected_fold_context(
            source,
            reviewed_sha256,
            preflight_path,
            run_directory,
            fold_id=fold_id,
            development_only_acknowledged=development_only_acknowledged,
            sha256_independently_reviewed=sha256_independently_reviewed,
        )
    except InferenceCancelledError:
        raise
    except Exception:  # noqa: BLE001 -- never echo private paths, rows or numerical exceptions
        failed = True
    if failed or result is None:
        raise SelectedFoldReplayError("GBmap selected-fold recovery failed closed") from None
    return result


def canonical_receipt_bytes(receipt: SelectedFoldReplayReceipt) -> bytes:
    checked = SelectedFoldReplayReceipt.model_validate(receipt.model_dump(mode="python"))
    payload = canonical_json_bytes(checked.model_dump(mode="json")) + b"\n"
    if len(payload) > _MAX_RECEIPT_BYTES:
        raise SelectedFoldReplayError("the selected-fold receipt exceeds its output bound")
    return payload


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> Never:
        sys.stderr.write("error: selected-fold replay arguments were not accepted\n")
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="replay-gbmap-selected-fold", description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--reviewed-sha256", required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--fold-id", required=True)
    parser.add_argument("--acknowledge-development-only", required=True, action="store_true")
    parser.add_argument(
        "--acknowledge-sha256-independently-reviewed", required=True, action="store_true"
    )
    args = parser.parse_args(argv)
    try:
        result = recover_selected_fold_context(
            args.source,
            args.reviewed_sha256,
            args.preflight,
            args.run_directory,
            fold_id=args.fold_id,
            development_only_acknowledged=args.acknowledge_development_only,
            sha256_independently_reviewed=args.acknowledge_sha256_independently_reviewed,
        )
        sys.stdout.write(canonical_receipt_bytes(result.receipt).decode())
    except InferenceCancelledError:
        raise
    except Exception:  # noqa: BLE001 -- sanitized private CLI boundary
        sys.stderr.write("error: GBmap selected-fold replay failed closed\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

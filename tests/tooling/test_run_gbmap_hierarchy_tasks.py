"""Adversarial tests for private resumable GBmap hierarchy execution."""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any, cast

import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.gbmap_deconvolution import (
    DEFAULT_TRAINING_CONFIGURATION,
    AggregateReference,
    GbmapExtractionResult,
    build_validation_split_plan,
)
from glio_proteogen.research.gbmap_deconvolution.training import _evaluate_prepared_fold
from tests.tooling import test_preflight_gbmap_development_candidate as base
from tools import fit_gbmap_development_candidate as fit_driver
from tools import preflight_gbmap_development_candidate as preflight_driver
from tools import run_gbmap_hierarchy_tasks as runner

if TYPE_CHECKING:
    from pathlib import Path

_REVIEWED_SHA256 = base._REVIEWED_SHA256


def _state() -> tuple[
    GbmapExtractionResult,
    preflight_driver.GbmapDevelopmentPreflightReceipt,
    runner.GbmapHierarchyRunManifest,
    tuple[runner._RuntimeTask, ...],
]:
    extraction = base._extraction()
    plan = build_validation_split_plan(extraction.reference)
    preflight = preflight_driver._build_receipt(
        extraction,
        plan,
        _REVIEWED_SHA256,
    )
    manifest, tasks = runner._build_manifest_and_tasks(extraction, plan, preflight)
    return extraction, preflight, manifest, tasks


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "private-source" / "scarches_core_GBmap.h5ad"
    source.parent.mkdir()
    source.write_bytes(b"mocked exact source; extraction remains in-memory in this test")
    return source


def _preflight_file(
    tmp_path: Path,
    receipt: preflight_driver.GbmapDevelopmentPreflightReceipt,
) -> Path:
    path = tmp_path / "private-receipts" / "preflight.json"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(preflight_driver.canonical_preflight_receipt_bytes(receipt))
    return path


def _install_extraction(monkeypatch: pytest.MonkeyPatch) -> GbmapExtractionResult:
    extraction = base._extraction()
    monkeypatch.setattr(
        runner,
        "extract_pinned_gbmap_reference",
        lambda *_args, **_kwargs: extraction,
    )
    return extraction


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    dry_run: bool,
    max_tasks: int = 1,
) -> tuple[Path, Path, runner.GbmapHierarchyBatchReceipt]:
    extraction = _install_extraction(monkeypatch)
    plan = build_validation_split_plan(extraction.reference)
    preflight = preflight_driver._build_receipt(extraction, plan, _REVIEWED_SHA256)
    source = _source(tmp_path)
    run_directory = tmp_path / "private-run"
    receipt = runner.run_batch(
        source,
        _REVIEWED_SHA256,
        _preflight_file(tmp_path, preflight),
        run_directory,
        max_tasks=max_tasks,
        dry_run=dry_run,
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
    )
    return source, run_directory, receipt


def _as_dict(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast("dict[str, object]", value)


def _redigest_checkpoint(document: dict[str, object]) -> bytes:
    evaluation = _as_dict(document["evaluation"])
    evaluation_body = {
        key: value for key, value in evaluation.items() if key != "evaluation_output_digest"
    }
    evaluation["evaluation_output_digest"] = sha256_digest(
        {"schema": runner.EVALUATION_OUTPUT_SCHEMA, **evaluation_body}
    )
    body = {key: value for key, value in document.items() if key != "checkpoint_digest"}
    document["checkpoint_digest"] = sha256_digest(body)
    return canonical_json_bytes(document) + b"\n"


def _replace_checkpoint_file(path: Path, payload: bytes) -> Path:
    document = cast("dict[str, object]", json.loads(payload))
    name = (
        cast("str", document["task_digest"]).removeprefix("sha256:")
        + "."
        + cast("str", document["checkpoint_digest"]).removeprefix("sha256:")
        + ".json"
    )
    replacement = path.with_name(name)
    path.unlink()
    replacement.write_bytes(payload)
    return replacement


def test_manifest_is_exact_lexical_bounded_and_schedules_only_evaluable_labels() -> None:
    extraction, preflight, manifest, tasks = _state()
    plan = build_validation_split_plan(extraction.reference)
    support = {
        (fold.fold_id, item.modeled_label): item.evaluable
        for fold in plan.folds
        for item in fold.label_support
    }

    assert manifest.task_count == len(tasks) == 56
    assert manifest.task_count == preflight.task_summary.validation_hierarchy_fit_upper_bound
    assert manifest.preflight_hierarchy_fit_upper_bound == 56
    assert tuple(
        (task.spec.fold_id, task.spec.shrinkage_index, task.spec.modeled_label) for task in tasks
    ) == tuple(
        sorted(
            (task.spec.fold_id, task.spec.shrinkage_index, task.spec.modeled_label)
            for task in tasks
        )
    )
    assert all(support[(task.spec.fold_id, task.spec.modeled_label)] for task in tasks)
    assert manifest.final_model_fitted is False
    assert manifest.runtime_mount_permitted is False
    assert manifest.public_http_mounted is False
    assert manifest.public_cli_mounted is False


def test_manifest_and_training_matrix_digests_are_input_order_invariant() -> None:
    extraction, preflight, manifest, _ = _state()
    reference = extraction.reference
    reordered = AggregateReference(
        feature_ids=reference.feature_ids,
        gene_symbols=reference.gene_symbols,
        records=tuple(reversed(reference.records)),
        source_file_sha256=reference.source_file_sha256,
        source_bytes=reference.source_bytes,
        taxonomy_digest=reference.taxonomy_digest,
        extraction_recipe_digest=reference.extraction_recipe_digest,
    )
    reordered_extraction = GbmapExtractionResult(
        reference=reordered,
        receipt=extraction.receipt,
    )
    reordered_plan = build_validation_split_plan(reordered)
    replay, _ = runner._build_manifest_and_tasks(
        reordered_extraction,
        reordered_plan,
        preflight,
    )

    assert replay == manifest


def test_dry_run_publishes_count_verified_manifest_without_executing_fit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden_fit(*args: object, **kwargs: object) -> object:
        del args, kwargs
        nonlocal called
        called = True
        raise AssertionError("dry run must not execute a hierarchy")

    monkeypatch.setattr(runner, "_fit_label", forbidden_fit)
    source, run_directory, receipt = _run(
        tmp_path,
        monkeypatch,
        dry_run=True,
        max_tasks=17,
    )

    assert called is False
    assert receipt.dry_run is True
    assert receipt.task_count == 56
    assert receipt.executed_task_count == 0
    assert receipt.remaining_task_count == 56
    assert (run_directory / runner.MANIFEST_NAME).is_file()
    assert list((run_directory / runner.CHECKPOINT_DIRECTORY_NAME).glob("*.json")) == []
    payload = (run_directory / runner.MANIFEST_NAME).read_bytes()
    assert runner.validate_manifest_json_bytes(payload).manifest_digest == receipt.manifest_digest
    assert str(source).encode() not in payload


def test_bounded_batches_resume_without_reexecuting_verified_shards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, run_directory, first = _run(tmp_path, monkeypatch, dry_run=False, max_tasks=1)
    assert first.executed_task_count == 1
    assert first.verified_checkpoint_count_before == 0
    first_files = tuple((run_directory / runner.CHECKPOINT_DIRECTORY_NAME).glob("*.json"))
    assert len(first_files) == 1
    first_bytes = first_files[0].read_bytes()

    extraction = _install_extraction(monkeypatch)
    plan = build_validation_split_plan(extraction.reference)
    preflight = preflight_driver._build_receipt(extraction, plan, _REVIEWED_SHA256)
    second = runner.run_batch(
        tmp_path / "private-source" / "scarches_core_GBmap.h5ad",
        _REVIEWED_SHA256,
        _preflight_file(tmp_path, preflight),
        run_directory,
        max_tasks=1,
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
    )

    assert second.verified_checkpoint_count_before == 1
    assert second.executed_task_count == 1
    assert second.verified_checkpoint_count_after == 2
    assert first_files[0].read_bytes() == first_bytes
    assert len(tuple((run_directory / runner.CHECKPOINT_DIRECTORY_NAME).glob("*.json"))) == 2


def test_checkpoint_is_content_addressed_private_and_provenance_replayable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, run_directory, _ = _run(tmp_path, monkeypatch, dry_run=False)
    manifest = runner.validate_manifest_json_bytes(
        (run_directory / runner.MANIFEST_NAME).read_bytes()
    )
    checkpoint_path = next((run_directory / runner.CHECKPOINT_DIRECTORY_NAME).glob("*.json"))
    payload = checkpoint_path.read_bytes()
    checkpoint = runner.validate_checkpoint_json_bytes(payload)
    _, _, expected_manifest, tasks = _state()
    assert manifest == expected_manifest
    task = next(item for item in tasks if item.spec.task_digest == checkpoint.task_digest)
    runner._validate_checkpoint_binding(checkpoint, manifest, task.spec, task)

    assert checkpoint_path.name == runner._checkpoint_filename(checkpoint)
    assert checkpoint.evaluation.state == "evaluated"
    assert checkpoint.evaluation.mean_per_count_nll is not None
    assert checkpoint.evaluation.evaluated_held_record_count > 0
    assert checkpoint.production_artifact_permitted is False
    assert checkpoint.runtime_mount_permitted is False
    assert b"private-donor" not in payload
    assert b"ENSG" not in payload
    assert str(source).encode() not in payload
    for forbidden in (
        b'"donor_key"',
        b'"feature_id"',
        b'"feature_indices"',
        b'"gene_counts"',
        b'"aggregate_content_digest"',
        b'"source_path"',
        b'"study_signatures"',
        b'"global_signature"',
        b'"concentration"',
    ):
        assert forbidden not in payload


def test_checkpoint_scores_have_bit_exact_parity_with_direct_fold_evaluation() -> None:
    _, _, manifest, tasks = _state()
    task = tasks[0]
    matching = tuple(
        candidate
        for candidate in tasks
        if candidate.spec.fold_id == task.spec.fold_id
        and candidate.spec.shrinkage_index == task.spec.shrinkage_index
    )
    checkpoints = tuple(runner._execute_task(manifest, candidate) for candidate in matching)
    scores: list[float] = []
    for checkpoint, candidate in zip(checkpoints, matching, strict=True):
        assert checkpoint.evaluation.state == "evaluated"
        score = checkpoint.evaluation.mean_per_count_nll
        assert score is not None
        scores.append(score)
        runner._validate_checkpoint_binding(
            checkpoint,
            manifest,
            candidate.spec,
            candidate,
        )
    direct = _evaluate_prepared_fold(
        task.prepared,
        task.spec.shrinkage,
        DEFAULT_TRAINING_CONFIGURATION.hierarchy,
        None,
    )

    assert direct.state == "evaluated"
    assert direct.mean_per_count_nll is not None
    assert math.fsum(scores) / len(scores) == direct.mean_per_count_nll
    assert (
        sum(item.evaluation.evaluated_held_record_count for item in checkpoints)
        == direct.evaluated_held_record_count
    )


def test_raw_checkpoint_tamper_is_rejected_before_source_extraction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, run_directory, _ = _run(tmp_path, monkeypatch, dry_run=False)
    checkpoint_path = next((run_directory / runner.CHECKPOINT_DIRECTORY_NAME).glob("*.json"))
    document = cast("dict[str, object]", json.loads(checkpoint_path.read_bytes()))
    evaluation = _as_dict(document["evaluation"])
    evaluation["mean_per_count_nll"] = cast("float", evaluation["mean_per_count_nll"]) + 1.0
    checkpoint_path.write_bytes(canonical_json_bytes(document) + b"\n")
    called = False

    def forbidden_extract(*args: object, **kwargs: object) -> object:
        del args, kwargs
        nonlocal called
        called = True
        raise AssertionError("tampered shard must fail before extraction")

    monkeypatch.setattr(runner, "extract_pinned_gbmap_reference", forbidden_extract)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError):
        runner.run_batch(
            tmp_path / "private-source" / "scarches_core_GBmap.h5ad",
            _REVIEWED_SHA256,
            tmp_path / "private-receipts" / "preflight.json",
            run_directory,
            max_tasks=1,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert called is False


def test_redigested_held_dimension_tamper_is_rejected_by_source_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, run_directory, _ = _run(tmp_path, monkeypatch, dry_run=False)
    checkpoint_path = next((run_directory / runner.CHECKPOINT_DIRECTORY_NAME).glob("*.json"))
    document = cast("dict[str, object]", json.loads(checkpoint_path.read_bytes()))
    evaluation = _as_dict(document["evaluation"])
    evaluation["evaluated_held_record_count"] = (
        cast("int", evaluation["evaluated_held_record_count"]) + 1
    )
    replacement = _redigest_checkpoint(document)
    _replace_checkpoint_file(checkpoint_path, replacement)

    _install_extraction(monkeypatch)
    with pytest.raises(
        runner.GbmapHierarchyTaskDriverError,
        match="provenance replay",
    ):
        runner.run_batch(
            tmp_path / "private-source" / "scarches_core_GBmap.h5ad",
            _REVIEWED_SHA256,
            tmp_path / "private-receipts" / "preflight.json",
            run_directory,
            max_tasks=1,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )


def test_manifest_tamper_and_noncanonical_bytes_fail_before_extraction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, run_directory, _ = _run(tmp_path, monkeypatch, dry_run=True)
    manifest_path = run_directory / runner.MANIFEST_NAME
    document = cast("dict[str, object]", json.loads(manifest_path.read_bytes()))
    document["task_count"] = cast("int", document["task_count"]) + 1
    manifest_path.write_bytes(json.dumps(document, indent=2).encode() + b"\n")
    called = False

    def forbidden_extract(*args: object, **kwargs: object) -> object:
        del args, kwargs
        nonlocal called
        called = True
        raise AssertionError("manifest tamper must fail before extraction")

    monkeypatch.setattr(runner, "extract_pinned_gbmap_reference", forbidden_extract)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError):
        runner.run_batch(
            tmp_path / "private-source" / "scarches_core_GBmap.h5ad",
            _REVIEWED_SHA256,
            tmp_path / "private-receipts" / "preflight.json",
            run_directory,
            max_tasks=1,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert called is False


@pytest.mark.parametrize("max_tasks", [0, -1, 257, True, 1.5])
def test_invalid_batch_bound_is_rejected_before_any_file_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    max_tasks: object,
) -> None:
    called = False

    def forbidden_read(*args: object, **kwargs: object) -> bytes:
        del args, kwargs
        nonlocal called
        called = True
        raise AssertionError("invalid bound must fail before receipt access")

    monkeypatch.setattr(runner, "_read_regular_bytes", forbidden_read)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="max_tasks"):
        runner.run_batch(
            tmp_path / "source.h5ad",
            _REVIEWED_SHA256,
            tmp_path / "preflight.json",
            tmp_path / "run",
            max_tasks=cast("Any", max_tasks),
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert called is False


def test_acknowledgements_are_required_before_receipt_or_source_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden(*args: object, **kwargs: object) -> object:
        del args, kwargs
        nonlocal called
        called = True
        raise AssertionError("acknowledgements must be checked first")

    monkeypatch.setattr(runner, "_read_regular_bytes", forbidden)
    monkeypatch.setattr(fit_driver, "_capture_source_snapshot", forbidden)
    with pytest.raises(fit_driver.GbmapDevelopmentFitDriverError):
        runner.run_batch(
            tmp_path / "source.h5ad",
            _REVIEWED_SHA256,
            tmp_path / "preflight.json",
            tmp_path / "run",
            max_tasks=1,
            development_only_acknowledged=False,
            sha256_independently_reviewed=True,
        )
    assert called is False


def test_run_directory_inside_repository_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extraction = _install_extraction(monkeypatch)
    plan = build_validation_split_plan(extraction.reference)
    preflight = preflight_driver._build_receipt(extraction, plan, _REVIEWED_SHA256)
    source = _source(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.setattr(fit_driver, "_REPOSITORY_ROOT", repository)

    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="outside the repository"):
        runner.run_batch(
            source,
            _REVIEWED_SHA256,
            _preflight_file(tmp_path, preflight),
            repository / "private-run",
            max_tasks=1,
            dry_run=True,
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )


def test_cli_error_is_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sensitive = tmp_path / "private-patient" / "source.h5ad"

    def failed(*args: object, **kwargs: object) -> runner.GbmapHierarchyBatchReceipt:
        del args, kwargs
        raise runner.GbmapHierarchyTaskDriverError(f"{sensitive}: private-donor")

    monkeypatch.setattr(runner, "run_batch", failed)
    result = runner.main(
        [
            str(sensitive),
            "--reviewed-sha256",
            _REVIEWED_SHA256,
            "--preflight",
            str(tmp_path / "preflight.json"),
            "--run-directory",
            str(tmp_path / "run"),
            "--dry-run",
            "--acknowledge-development-only",
            "--acknowledge-sha256-independently-reviewed",
        ]
    )
    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: GBmap hierarchy task batch failed closed\n"
    assert str(sensitive) not in captured.err

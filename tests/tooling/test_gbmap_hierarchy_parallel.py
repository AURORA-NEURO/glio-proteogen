"""Independent scheduling oracles for bounded GBmap task concurrency."""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

import json
from dataclasses import replace
from threading import Barrier, Event, Lock, get_ident
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbmap_deconvolution import (
    DEFAULT_TRAINING_CONFIGURATION,
    GbmapExtractionReceipt,
    GbmapExtractionResult,
    build_validation_split_plan,
)
from tests.tooling import test_run_gbmap_hierarchy_tasks as base
from tools import preflight_gbmap_development_candidate as preflight_driver
from tools import run_gbmap_hierarchy_tasks as runner

if TYPE_CHECKING:
    from pathlib import Path

RunInputs = tuple["Path", "Path", "Path"]


def _extraction() -> GbmapExtractionResult:
    """Keep real low-shrinkage fits and a genuine held-score abstention.

    Only this file's synthetic reference gains the unselected sentinel. Counts
    remain exactly20,000 per row; the base cached fixtures remain unchanged.
    """

    original = base.base._extraction()
    first_study = min(row.study_key for row in original.reference.records)
    records = []
    for row in original.reference.records:
        if row.study_key == first_study and row.modeled_label == "NPC-like":
            counts = np.zeros(25, dtype=np.int64)
            detected = np.zeros(25, dtype=np.int32)
            counts[-1], detected[-1] = row.total_umis, 30
        else:
            counts = np.concatenate((row.gene_counts, np.zeros(1, dtype=np.int64)))
            detected = np.concatenate((row.detected_cell_counts, np.zeros(1, dtype=np.int32)))
        records.append(replace(row, gene_counts=counts, detected_cell_counts=detected))
    reference = replace(
        original.reference,
        feature_ids=(*original.reference.feature_ids, "ENSG-SYNTHETIC-SENTINEL"),
        gene_symbols=(*original.reference.gene_symbols, "SYNTHETIC-SENTINEL"),
        records=tuple(records),
    )
    fields = original.receipt.model_dump(exclude={"receipt_digest"})
    fields["feature_order_digest"] = reference.feature_order_digest
    receipt = GbmapExtractionReceipt.model_validate(
        {**fields, "receipt_digest": sha256_digest(fields)}
    )
    return GbmapExtractionResult(reference=reference, receipt=receipt)


def _state():
    extraction = _extraction()
    plan = build_validation_split_plan(extraction.reference)
    preflight = preflight_driver._build_receipt(extraction, plan, base._REVIEWED_SHA256)
    manifest, tasks = runner._build_manifest_and_tasks(extraction, plan, preflight)
    return extraction, preflight, manifest, tasks


def _scheduling_checkpoint(manifest, task):
    """A legal task-bound output oracle for scheduling tests, without fitting."""

    evaluation = runner._evaluation_output(
        state="abstained", reason="hierarchy_fit_failed", fit=None
    )
    body = runner._checkpoint_body(manifest, task.spec, evaluation)
    return runner.GbmapHierarchyCheckpoint.model_validate(
        {**body, "checkpoint_digest": sha256_digest(body), "evaluation": evaluation}
    )


def _inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunInputs:
    tmp_path.mkdir(parents=True, exist_ok=True)
    extraction = _extraction()
    monkeypatch.setattr(runner, "extract_pinned_gbmap_reference", lambda *_a, **_kw: extraction)
    plan = build_validation_split_plan(extraction.reference)
    preflight = preflight_driver._build_receipt(extraction, plan, base._REVIEWED_SHA256)
    return (
        base._source(tmp_path),
        base._preflight_file(tmp_path, preflight),
        tmp_path / "private-run",
    )


def _run(
    inputs: RunInputs,
    *,
    workers: int | None = 1,
    max_tasks: int = 4,
    dry_run: bool = False,
) -> runner.GbmapHierarchyBatchReceipt:
    source, preflight, output = inputs
    options = {} if workers is None else {"workers": workers}
    return runner.run_batch(
        source,
        base._REVIEWED_SHA256,
        preflight,
        output,
        max_tasks=max_tasks,
        dry_run=dry_run,
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
        **options,
    )


def _files(output: Path) -> dict[str, bytes]:
    return {
        path.relative_to(output).as_posix(): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }


def _checkpoints(output: Path) -> tuple[runner.GbmapHierarchyCheckpoint, ...]:
    return tuple(
        runner.validate_checkpoint_json_bytes(path.read_bytes())
        for path in (output / runner.CHECKPOINT_DIRECTORY_NAME).glob("*.json")
    )


def test_synthetic_sentinel_preserves_training_geometry_and_cached_fixture_isolation() -> None:
    original = base.base._extraction()
    original_digest = original.reference.aggregate_content_digest
    extraction, _preflight, _manifest, tasks = _state()
    assert extraction.reference is not original.reference
    assert len(extraction.reference.feature_ids) == 25
    assert len(original.reference.feature_ids) == 24
    assert original.reference.aggregate_content_digest == original_digest
    assert all(len(row.gene_counts) == 24 for row in original.reference.records)
    first = tasks[0].prepared
    _old_extraction, _old_preflight, _old_manifest, original_tasks = base._state()
    assert len(tasks) >= 8
    assert first.feature_indices == original_tasks[0].prepared.feature_indices
    assert 24 not in first.feature_indices
    assert all(row.gene_counts[-1] == 0 for row in first.training_records)
    assert all(row.total_umis == 20_000 for row in extraction.reference.records)
    held_npc = [row for row in first.held_records if row.modeled_label == "NPC-like"]
    held_mes = [row for row in first.held_records if row.modeled_label == "MES-like"]
    assert len(held_npc) == len(held_mes) == 3
    assert all(int(row.gene_counts[-1]) == 20_000 for row in held_npc)
    assert all(sum(map(int, row.gene_counts[:-1])) == 0 for row in held_npc)
    assert all(int(row.gene_counts[-1]) == 0 for row in held_mes)
    assert all(row.eligible_for_reference for row in extraction.reference.records)


@pytest.mark.parametrize("workers", [2, 4])
def test_parallel_checkpoint_and_batch_bytes_equal_the_default_serial_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workers: int,
) -> None:
    fits = []
    original_fit = runner._fit_label

    def fit(*args, **kwargs):
        assert kwargs["configuration"] is DEFAULT_TRAINING_CONFIGURATION.hierarchy
        fits.append((kwargs["reference"], kwargs["label"], kwargs["shrinkage"]))
        return original_fit(*args, **kwargs)

    monkeypatch.setattr(runner, "_fit_label", fit)
    serial_inputs = _inputs(tmp_path / "serial", monkeypatch)
    serial = _run(serial_inputs, workers=None, max_tasks=4)
    parallel_inputs = _inputs(tmp_path / "parallel", monkeypatch)
    parallel = _run(parallel_inputs, workers=workers, max_tasks=4)

    assert _files(serial_inputs[2]) == _files(parallel_inputs[2])
    assert runner.canonical_batch_receipt_bytes(serial) == runner.canonical_batch_receipt_bytes(
        parallel
    )
    assert serial.executed_task_count == parallel.executed_task_count == 4
    assert len(fits) == 8
    assert len({id(reference) for reference, _label, _shrinkage in fits[:4]}) == 1
    assert len({id(reference) for reference, _label, _shrinkage in fits[4:]}) == 1
    assert fits[0][0] is not fits[4][0]
    expected_fits = [
        (label, shrinkage) for shrinkage in (0.1, 1.0) for label in ("MES-like", "NPC-like")
    ]
    assert sorted((label, shrinkage) for _reference, label, shrinkage in fits[:4]) == sorted(
        expected_fits
    )
    assert sorted((label, shrinkage) for _reference, label, shrinkage in fits[4:]) == sorted(
        expected_fits
    )
    assert {checkpoint.evaluation.state for checkpoint in _checkpoints(serial_inputs[2])} == {
        "evaluated",
        "abstained",
    }
    for checkpoint in _checkpoints(serial_inputs[2]):
        if checkpoint.modeled_label == "MES-like":
            assert checkpoint.evaluation.state == "evaluated"
        else:
            assert checkpoint.evaluation.abstention_reason == "no_positive_held_marker_counts"


def test_reverse_worker_completion_still_publishes_lexically_on_the_owning_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs(tmp_path, monkeypatch)
    _, _, _, tasks = _state()
    scheduled = tuple(task.spec.task_digest for task in tasks[:4])
    ordinal = {digest: index for index, digest in enumerate(scheduled)}
    events = tuple(Event() for _ in scheduled)
    completed: list[str] = []
    published: list[str] = []
    published_checkpoint_digests: list[str] = []
    publisher_threads: list[int] = []
    original_publish = runner._publish_checkpoint
    owner = get_ident()

    def execute(manifest, task):
        index = ordinal[task.spec.task_digest]
        if index < len(events) - 1:
            assert events[index + 1].wait(timeout=10)
        result = _scheduling_checkpoint(manifest, task)
        completed.append(task.spec.task_digest)
        events[index].set()
        return result

    def publish(output, source, checkpoint):
        published.append(checkpoint.task_digest)
        published_checkpoint_digests.append(checkpoint.checkpoint_digest)
        publisher_threads.append(get_ident())
        original_publish(output, source, checkpoint)

    monkeypatch.setattr(runner, "_execute_task", execute)
    monkeypatch.setattr(runner, "_publish_checkpoint", publish)
    receipt = _run(inputs, workers=4)

    assert completed == list(reversed(scheduled))
    assert published == list(scheduled)
    assert publisher_threads == [owner] * 4
    assert receipt.checkpoint_digests == tuple(published_checkpoint_digests)
    assert receipt.executed_task_count == 4


@pytest.mark.parametrize("workers", [2, 4])
def test_scheduler_concurrency_reaches_but_never_exceeds_the_requested_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workers: int,
) -> None:
    inputs = _inputs(tmp_path, monkeypatch)
    barrier = Barrier(workers)
    lock = Lock()
    active = peak = total = 0

    def execute(manifest, task):
        nonlocal active, peak, total
        with lock:
            active += 1
            total += 1
            peak = max(peak, active)
        try:
            barrier.wait(timeout=10)
            return _scheduling_checkpoint(manifest, task)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(runner, "_execute_task", execute)
    receipt = _run(inputs, workers=workers, max_tasks=workers * 2)

    assert peak == workers
    assert active == 0
    assert total == receipt.executed_task_count == workers * 2


def test_worker_failure_is_sanitized_and_resume_preserves_only_the_published_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs(tmp_path, monkeypatch)
    _, _, _, tasks = _state()
    scheduled = tuple(task.spec.task_digest for task in tasks[:4])
    calls: list[str] = []

    def execute(manifest, task):
        calls.append(task.spec.task_digest)
        if task.spec.task_digest == scheduled[1]:
            raise OSError("sensitive-synthetic-donor/private-source-path")
        return _scheduling_checkpoint(manifest, task)

    monkeypatch.setattr(runner, "_execute_task", execute)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError) as failure:
        _run(inputs, workers=4)
    assert str(failure.value) == "GBmap hierarchy task execution failed closed"
    assert failure.value.__suppress_context__ is True
    before = _files(inputs[2])
    checkpoints = _checkpoints(inputs[2])
    assert tuple(checkpoint.task_digest for checkpoint in checkpoints) == scheduled[:1]

    replayed: list[str] = []

    def resume(manifest, task):
        replayed.append(task.spec.task_digest)
        return _scheduling_checkpoint(manifest, task)

    monkeypatch.setattr(runner, "_execute_task", resume)
    receipt = _run(inputs, workers=2, max_tasks=3)
    assert receipt.verified_checkpoint_count_before == 1
    assert receipt.executed_task_count == 3
    assert receipt.verified_checkpoint_count_after == 4
    assert set(replayed) == set(scheduled[1:])
    assert scheduled[0] not in replayed
    after = _files(inputs[2])
    assert all(after[name] == payload for name, payload in before.items())


@pytest.mark.parametrize("workers", [True, False, 0, 5, 2.0, "2"])
def test_invalid_worker_type_or_bound_is_rejected_before_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workers: object,
) -> None:
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        del args, kwargs
        calls.append("access")
        raise AssertionError("invalid worker bounds must precede all I/O")

    for name in ("_read_regular_bytes", "_inspect_private_directory", "ThreadPoolExecutor"):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr(runner.fit_driver, "_capture_source_snapshot", forbidden)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="workers"):
        runner.run_batch(
            tmp_path / "absent-source.h5ad",
            base._REVIEWED_SHA256,
            tmp_path / "absent-preflight.json",
            tmp_path / "absent-output",
            max_tasks=1,
            workers=cast("Any", workers),
            development_only_acknowledged=True,
            sha256_independently_reviewed=True,
        )
    assert calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_dry_run_never_constructs_an_executor_or_executes_any_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workers: int,
) -> None:
    inputs = _inputs(tmp_path, monkeypatch)

    def forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("a dry run must not create workers or fit tasks")

    monkeypatch.setattr(runner, "ThreadPoolExecutor", forbidden)
    monkeypatch.setattr(runner, "_execute_task", forbidden)
    receipt = _run(inputs, workers=workers, max_tasks=8, dry_run=True)
    assert receipt.executed_task_count == 0
    assert receipt.dry_run is True
    assert _checkpoints(inputs[2]) == ()


def test_parallel_resume_rejects_a_redigested_checkpoint_before_scheduling_new_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs(tmp_path, monkeypatch)
    _run(inputs, workers=1, max_tasks=1)
    path = next((inputs[2] / runner.CHECKPOINT_DIRECTORY_NAME).glob("*.json"))
    document = cast("dict[str, object]", json.loads(path.read_bytes()))
    evaluation = base._as_dict(document["evaluation"])
    evaluation["evaluated_held_record_count"] = (
        cast("int", evaluation["evaluated_held_record_count"]) + 1
    )
    base._replace_checkpoint_file(path, base._redigest_checkpoint(document))

    def forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("tampered checkpoint must fail before any new task scheduling")

    monkeypatch.setattr(runner, "ThreadPoolExecutor", forbidden)
    monkeypatch.setattr(runner, "_execute_task", forbidden)
    with pytest.raises(runner.GbmapHierarchyTaskDriverError, match="provenance replay"):
        _run(inputs, workers=4)


def test_cli_forwards_worker_count_and_sanitizes_a_worker_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    called: list[int] = []

    def failed(*args, **kwargs):
        del args
        called.append(kwargs["workers"])
        raise runner.GbmapHierarchyTaskDriverError("synthetic-private-path/sensitive-donor")

    monkeypatch.setattr(runner, "run_batch", failed)
    assert (
        runner.main(
            [
                str(tmp_path / "private.h5ad"),
                "--reviewed-sha256",
                base._REVIEWED_SHA256,
                "--preflight",
                str(tmp_path / "preflight.json"),
                "--run-directory",
                str(tmp_path / "run"),
                "--workers",
                "4",
                "--acknowledge-development-only",
                "--acknowledge-sha256-independently-reviewed",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert called == [4]
    assert captured.out == ""
    assert captured.err == "error: GBmap hierarchy task batch failed closed\n"


@pytest.fixture
def cli_work_tripwire(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        del args, kwargs
        calls.append("backend work")
        pytest.fail("argument parsing must precede all private I/O and task execution")

    for name in (
        "run_batch",
        "_read_regular_bytes",
        "_inspect_private_directory",
        "_execute_task",
        "ThreadPoolExecutor",
    ):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr(runner.fit_driver, "_capture_source_snapshot", forbidden)
    return calls


def _private_cli_arguments(sentinel: str) -> list[str]:
    return [
        f"{sentinel}/source.h5ad",
        "--reviewed-sha256",
        base._REVIEWED_SHA256,
        "--preflight",
        f"{sentinel}/preflight.json",
        "--run-directory",
        f"{sentinel}/run",
        "--acknowledge-development-only",
        "--acknowledge-sha256-independently-reviewed",
    ]


@pytest.mark.parametrize("option", ["--workers", "--max-tasks"])
@pytest.mark.parametrize("value", ["SYNTHETIC_PRIVATE_ARGUMENT/value", "1.5", "nan"])
def test_cli_malformed_integer_limits_do_not_echo_private_arguments_or_start_work(
    capsys: pytest.CaptureFixture[str],
    cli_work_tripwire: list[str],
    option: str,
    value: str,
) -> None:
    sentinel = "SYNTHETIC_PRIVATE_ARGUMENT"
    with pytest.raises(SystemExit) as failure:
        runner.main([*_private_cli_arguments(sentinel), option, value])

    captured = capsys.readouterr()
    assert failure.value.code == 2
    assert captured.out == ""
    assert captured.err == "error: hierarchy task arguments were not accepted\n"
    assert sentinel not in captured.out + captured.err
    assert value not in captured.out + captured.err
    assert cli_work_tripwire == []


@pytest.mark.parametrize(
    "kind",
    [
        "missing_all",
        "missing_source",
        "missing_required",
        "missing_workers",
        "missing_max_tasks",
        "unknown",
    ],
)
def test_cli_missing_or_unknown_arguments_do_not_echo_private_material_or_start_work(
    capsys: pytest.CaptureFixture[str],
    cli_work_tripwire: list[str],
    kind: str,
) -> None:
    sentinel = "SYNTHETIC_PRIVATE_ARGUMENT"
    arguments = _private_cli_arguments(sentinel)
    if kind == "missing_all":
        arguments = []
    elif kind == "missing_source":
        arguments = arguments[1:]
    elif kind == "missing_required":
        arguments = arguments[:1]
    elif kind == "missing_workers":
        arguments.append("--workers")
    elif kind == "missing_max_tasks":
        arguments.append("--max-tasks")
    else:
        arguments.extend(["--unrecognized-option", sentinel])

    with pytest.raises(SystemExit) as failure:
        runner.main(arguments)

    captured = capsys.readouterr()
    assert failure.value.code == 2
    assert captured.out == ""
    assert captured.err == "error: hierarchy task arguments were not accepted\n"
    assert sentinel not in captured.out + captured.err
    assert cli_work_tripwire == []


@pytest.mark.parametrize("include_private_argument", [False, True])
def test_cli_help_is_static_and_never_starts_private_io_or_task_execution(
    capsys: pytest.CaptureFixture[str],
    cli_work_tripwire: list[str],
    *,
    include_private_argument: bool,
) -> None:
    sentinel = "SYNTHETIC_PRIVATE_ARGUMENT"
    arguments = ["--help", sentinel] if include_private_argument else ["--help"]
    with pytest.raises(SystemExit) as failure:
        runner.main(arguments)

    captured = capsys.readouterr()
    assert failure.value.code == 0
    assert "usage:" in captured.out
    assert "--workers" in captured.out
    assert "--max-tasks" in captured.out
    assert captured.err == ""
    assert sentinel not in captured.out
    assert cli_work_tripwire == []

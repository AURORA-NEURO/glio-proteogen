"""Executor resume provenance guards with closed synthetic failed checkpoints.

Manifest, task and checkpoint seals come from the real builders/validators.
The saved failed-task outputs are controlled metadata fixtures, not numerical
fit evidence. No successful fit or private source admission is fabricated.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.gbmap_deconvolution import (
    GbmapExtractionReceipt,
    GbmapExtractionResult,
    build_validation_split_plan,
)
from tests.tooling import test_run_gbmap_hierarchy_tasks as fixture
from tools import preflight_gbmap_development_candidate as preflight_driver
from tools import run_gbmap_hierarchy_tasks as runner


def _failed_checkpoint(manifest, task):
    evaluation = runner._evaluation_output(
        state="abstained", reason="hierarchy_fit_failed", fit=None
    )
    body = runner._checkpoint_body(manifest, task.spec, evaluation)
    return runner.GbmapHierarchyCheckpoint.model_validate(
        {**body, "checkpoint_digest": sha256_digest(body), "evaluation": evaluation}
    )


def _prepare(tmp_path, preflight, manifest, checkpoint, *, save_manifest=True):
    source = fixture._source(tmp_path)
    preflight_path = fixture._preflight_file(tmp_path, preflight)
    directory = tmp_path / "private-run"
    checkpoints = directory / runner.CHECKPOINT_DIRECTORY_NAME
    checkpoints.mkdir(parents=True)
    if save_manifest:
        payload = runner.canonical_manifest_bytes(manifest)
        assert runner.validate_manifest_json_bytes(payload) == manifest
        (directory / runner.MANIFEST_NAME).write_bytes(payload)
    payload = runner.canonical_checkpoint_bytes(checkpoint)
    assert runner.validate_checkpoint_json_bytes(payload) == checkpoint
    (checkpoints / runner._checkpoint_filename(checkpoint)).write_bytes(payload)
    return source, preflight_path, directory


def _inventory(directory):
    return {
        path.relative_to(directory).as_posix(): None if path.is_dir() else path.read_bytes()
        for path in directory.rglob("*")
    }


def _forbid(monkeypatch, calls, names):
    def blocked(name):
        def action(*_args, **_kwargs):
            calls.append(name)
            pytest.fail(f"rejected resume must stop before {name}")

        return action

    for name in names:
        monkeypatch.setattr(runner, name, blocked(name))


def _run(inputs):
    return runner.run_batch(
        inputs[0],
        fixture._REVIEWED_SHA256,
        inputs[1],
        inputs[2],
        max_tasks=1,
        workers=4,
        development_only_acknowledged=True,
        sha256_independently_reviewed=True,
    )


def test_orphan_canonical_checkpoint_stops_before_source_or_publication_and_retains_bytes(
    tmp_path, monkeypatch
):
    _extraction, preflight, manifest, tasks = fixture._state()
    checkpoint = _failed_checkpoint(manifest, tasks[0])
    runner._validate_checkpoint_binding(checkpoint, manifest, tasks[0].spec, None)
    inputs = _prepare(tmp_path, preflight, manifest, checkpoint, save_manifest=False)
    before = _inventory(tmp_path)
    calls = []
    _forbid(
        monkeypatch,
        calls,
        (
            "extract_pinned_gbmap_reference",
            "_fit_label",
            "_execute_private_task",
            "_publish_manifest",
            "_publish_checkpoint",
            "ThreadPoolExecutor",
        ),
    )

    def forbidden_snapshot(*_args):
        calls.append("source snapshot")
        pytest.fail("orphan checkpoints must fail before source access")

    monkeypatch.setattr(runner.fit_driver, "_capture_source_snapshot", forbidden_snapshot)
    with pytest.raises(
        runner.GbmapHierarchyTaskDriverError,
        match="checkpoints cannot exist without a run manifest",
    ):
        _run(inputs)
    assert calls == []
    assert _inventory(tmp_path) == before
    assert not (inputs[2] / runner.MANIFEST_NAME).exists()


def _alternate_extraction(original, change):
    reference = original.reference
    if change == "training_counts":
        first = reference.records[0]
        counts = first.gene_counts.copy()
        counts[0] += 1
        counts[1] -= 1
        records = (replace(first, gene_counts=counts), *reference.records[1:])
        changed = replace(reference, records=records)
    else:
        order = tuple(reversed(range(len(reference.feature_ids))))
        records = tuple(
            replace(
                row,
                gene_counts=row.gene_counts[list(order)],
                detected_cell_counts=row.detected_cell_counts[list(order)],
            )
            for row in reference.records
        )
        changed = replace(
            reference,
            feature_ids=tuple(reference.feature_ids[index] for index in order),
            gene_symbols=tuple(reference.gene_symbols[index] for index in order),
            records=records,
        )
    assert changed.aggregate_content_digest != reference.aggregate_content_digest
    assert len(changed.feature_ids) == len(reference.feature_ids)
    assert [row.total_umis for row in changed.records] == [
        row.total_umis for row in reference.records
    ]
    fields = original.receipt.model_dump(mode="python", exclude={"receipt_digest"})
    fields["feature_order_digest"] = changed.feature_order_digest
    receipt = GbmapExtractionReceipt.model_validate(
        {**fields, "receipt_digest": sha256_digest(fields)}
    )
    return GbmapExtractionResult(reference=changed, receipt=receipt)


@pytest.mark.parametrize("change", ["training_counts", "ordered_feature_axis"])
def test_fully_sealed_alternate_basis_stops_before_new_work_and_preserves_every_byte(
    tmp_path, monkeypatch, change
):
    extraction, preflight, original_manifest, original_tasks = fixture._state()
    alternate = _alternate_extraction(extraction, change)
    plan = build_validation_split_plan(alternate.reference)
    alternate_preflight = preflight_driver._build_receipt(alternate, plan, fixture._REVIEWED_SHA256)
    manifest, tasks = runner._build_manifest_and_tasks(alternate, plan, alternate_preflight)
    assert manifest != original_manifest
    assert manifest.task_count == original_manifest.task_count
    assert manifest.reviewed_sha256 == original_manifest.reviewed_sha256
    assert manifest.source_bytes == original_manifest.source_bytes
    assert tuple(
        (task.spec.fold_id, task.spec.shrinkage_index, task.spec.modeled_label) for task in tasks
    ) == tuple(
        (task.spec.fold_id, task.spec.shrinkage_index, task.spec.modeled_label)
        for task in original_tasks
    )
    originals = {
        (task.spec.fold_id, task.spec.shrinkage_index, task.spec.modeled_label): task
        for task in original_tasks
    }
    task = next(
        task
        for task in tasks
        if task.spec.training_matrix_digest
        != originals[
            (task.spec.fold_id, task.spec.shrinkage_index, task.spec.modeled_label)
        ].spec.training_matrix_digest
    )
    if change == "ordered_feature_axis":
        assert manifest.feature_order_digest != original_manifest.feature_order_digest
    else:
        assert manifest.feature_order_digest == original_manifest.feature_order_digest
    checkpoint = _failed_checkpoint(manifest, task)
    # A valid seal and declared task provenance alone cannot prove source basis.
    runner._validate_checkpoint_binding(checkpoint, manifest, task.spec, task)
    inputs = _prepare(tmp_path, preflight, manifest, checkpoint)
    before = _inventory(tmp_path)
    calls = []
    handles = []
    actual_guard = runner.fit_driver._open_source_guard

    def extract(source, **_kwargs):
        assert source == inputs[0]
        calls.append("extract")
        return extraction

    def guard(snapshot):
        handle = actual_guard(snapshot)
        handles.append(handle)
        return handle

    monkeypatch.setattr(runner, "extract_pinned_gbmap_reference", extract)
    monkeypatch.setattr(runner.fit_driver, "_open_source_guard", guard)
    _forbid(
        monkeypatch,
        calls,
        (
            "_fit_label",
            "_execute_private_task",
            "_publish_manifest",
            "_publish_checkpoint",
            "ThreadPoolExecutor",
        ),
    )
    with pytest.raises(
        runner.GbmapHierarchyTaskDriverError,
        match="run manifest does not match deterministic replay",
    ):
        _run(inputs)
    assert calls == ["extract"]
    assert len(handles) == 1
    assert handles[0].closed
    assert _inventory(tmp_path) == before
    assert (inputs[2] / runner.MANIFEST_NAME).read_bytes() == runner.canonical_manifest_bytes(
        manifest
    )

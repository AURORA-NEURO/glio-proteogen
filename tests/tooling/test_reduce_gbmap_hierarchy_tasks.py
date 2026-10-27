"""Private reduction CLI integrity tests using synthetic sealed task evidence."""

# ruff: noqa: PLR2004 -- compact synthetic fixtures and deliberate private failures

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.gbmap_development_reduction import ReductionError
from tests.research import test_gbmap_development_reduction as core
from tools import reduce_gbmap_hierarchy_tasks as driver
from tools import run_gbmap_hierarchy_tasks as tasks


def _forbidden(*_args, **_kwargs):
    pytest.fail("metadata-only assessment or an invalid reduction reached source/model work")


def _old_manifest(manifest):
    return tasks.GbmapHierarchyRunManifest.model_validate(manifest.model_dump(mode="python"))


def _old_checkpoint(row):
    return tasks.GbmapHierarchyCheckpoint.model_validate(row.model_dump(mode="python"))


def _write_checkpoint(directory, row):
    checkpoint = _old_checkpoint(row)
    path = directory / tasks.CHECKPOINT_DIRECTORY_NAME / tasks._checkpoint_filename(checkpoint)
    path.write_bytes(tasks.canonical_checkpoint_bytes(checkpoint))
    return path


@pytest.fixture
def saved_run(tmp_path, monkeypatch):
    manifest, rows = core._fixture()
    directory = tmp_path / "private-run"
    directory.mkdir()
    (directory / tasks.CHECKPOINT_DIRECTORY_NAME).mkdir()
    (directory / tasks.MANIFEST_NAME).write_bytes(
        tasks.canonical_manifest_bytes(_old_manifest(manifest))
    )
    paths = tuple(_write_checkpoint(directory, row) for row in rows)
    source = tmp_path / "private-source.h5ad"
    source.write_bytes(b"small synthetic source; full source replay is mocked")
    preflight = tmp_path / "private-preflight.json"
    preflight.write_bytes(b"synthetic replay input; not parsed by the mock")
    monkeypatch.setattr(driver, "method_digest", lambda: core._hash("current-method"))
    return SimpleNamespace(
        manifest=manifest,
        rows=rows,
        paths=paths,
        directory=directory,
        source=source,
        preflight=preflight,
        replay_calls=[],
    )


def _mock_replay(monkeypatch, saved_run, *, action=None, complete=True, wrong_manifest=False):
    def replay(source, reviewed_sha256, preflight_path, directory, **kwargs):
        saved_run.replay_calls.append((source, reviewed_sha256, preflight_path, directory, kwargs))
        assert kwargs["dry_run"] is True
        assert kwargs["max_tasks"] == 1
        if action is not None:
            action()
        return SimpleNamespace(
            manifest_digest=core._hash("wrong manifest")
            if wrong_manifest
            else saved_run.manifest.manifest_digest,
            run_complete=complete,
            receipt_digest=core._hash("source-replay-receipt"),
        )

    monkeypatch.setattr(tasks, "run_batch", replay)


def _reduce(saved_run, **changes):
    return driver.reduce_run(
        saved_run.source,
        saved_run.manifest.reviewed_sha256,
        saved_run.preflight,
        saved_run.directory,
        development_only_acknowledged=changes.get("development_only_acknowledged", True),
        sha256_independently_reviewed=changes.get("sha256_independently_reviewed", True),
    )


def _sealed_bundle(document):
    result = deepcopy(document)
    result.pop("bundle_digest", None)
    return {**result, "bundle_digest": sha256_digest(result)}


def test_assess_reads_only_saved_plan_and_does_not_claim_source_or_numerical_verification(
    monkeypatch, saved_run
):
    (saved_run.directory / tasks.CHECKPOINT_DIRECTORY_NAME / "private-unread-entry").write_bytes(
        b"invalid"
    )
    for module, name in (
        (tasks, "run_batch"),
        (tasks, "_load_checkpoints"),
        (driver.fit_driver, "_capture_source_snapshot"),
        (driver.fit_driver, "_open_source_guard"),
        (driver, "reduce_completed_validation"),
    ):
        monkeypatch.setattr(module, name, _forbidden)
    bundle = driver.assess_run(saved_run.directory)
    assert bundle.verification_kind == "saved_plan_feasibility"
    assert bundle.selection is bundle.source_replay_receipt_digest is None
    assert bundle.planning.planning_gate_status == "potentially_feasible"
    assert bundle.planning.numerical_or_marker_success_established is False
    assert bundle.planning.model_selection_performed is False
    assert "private-" not in driver.canonical_bundle_bytes(bundle).decode()


def test_reduce_replays_source_and_every_saved_task_before_exact_reduction(monkeypatch, saved_run):
    _mock_replay(monkeypatch, saved_run)
    bundle = _reduce(saved_run)
    assert bundle.verification_kind == "source_replayed_complete_task_reduction"
    assert bundle.source_replay_receipt_digest == core._hash("source-replay-receipt")
    expected = core.reduce_completed_validation(saved_run.manifest, saved_run.rows)
    assert bundle.selection == expected
    assert expected.selected_shrinkage == 1.0
    assert expected.final_model_fitted is False
    assert expected.model_artifact_emitted is False
    assert expected.runtime_mount_permitted is False
    assert len(saved_run.replay_calls) == 1
    source, reviewed, preflight, directory, kwargs = saved_run.replay_calls[0]
    assert (source, reviewed, preflight, directory) == (
        saved_run.source,
        saved_run.manifest.reviewed_sha256,
        saved_run.preflight,
        saved_run.directory,
    )
    assert kwargs["development_only_acknowledged"] is True
    assert kwargs["sha256_independently_reviewed"] is True


@pytest.mark.parametrize("kind", ["incomplete", "extra_entry", "tampered_bytes", "foreign_profile"])
def test_incomplete_extra_or_unbound_shards_fail_before_expensive_replay(
    monkeypatch, saved_run, kind
):
    if kind == "incomplete":
        saved_run.paths[0].unlink()
    elif kind == "extra_entry":
        (saved_run.directory / tasks.CHECKPOINT_DIRECTORY_NAME / "unreviewed.json").write_bytes(
            b"{}"
        )
    elif kind == "tampered_bytes":
        saved_run.paths[0].write_bytes(
            saved_run.paths[0]
            .read_bytes()
            .replace(b'"mean_per_count_nll":1.0', b'"mean_per_count_nll":9.0')
        )
    else:
        saved_run.paths[0].unlink()
        _write_checkpoint(
            saved_run.directory,
            core._checkpoint(saved_run.rows[0], profile_digest=core._hash("foreign profile")),
        )
    monkeypatch.setattr(tasks, "run_batch", _forbidden)
    monkeypatch.setattr(driver.fit_driver, "_capture_source_snapshot", _forbidden)
    with pytest.raises((ReductionError, tasks.GbmapHierarchyTaskDriverError)):
        _reduce(saved_run)


@pytest.mark.parametrize(
    "kind",
    [
        "manifest_change",
        "wrong_replay_manifest",
        "incomplete_replay",
        "checkpoint_change",
        "checkpoint_remove",
        "checkpoint_add",
    ],
)
def test_run_must_stay_identical_across_source_replay(monkeypatch, saved_run, kind):
    def action():
        if kind == "manifest_change":
            document = saved_run.manifest.model_dump(mode="python")
            document["profile_digest"] = core._hash("changed manifest")
            changed = core._manifest(document)
            (saved_run.directory / tasks.MANIFEST_NAME).write_bytes(
                tasks.canonical_manifest_bytes(_old_manifest(changed))
            )
        elif kind == "checkpoint_change":
            row = saved_run.rows[0]
            evaluation = row.evaluation.model_dump(mode="python")
            evaluation["mean_per_count_nll"] = 9.0
            evaluation = core._seal(
                evaluation, "evaluation_output_digest", "gbmap-hierarchy-evaluation-output/1.0.0"
            )
            saved_run.paths[0].unlink()
            _write_checkpoint(saved_run.directory, core._checkpoint(row, evaluation=evaluation))
        elif kind == "checkpoint_remove":
            saved_run.paths[0].unlink()
        elif kind == "checkpoint_add":
            (saved_run.directory / tasks.CHECKPOINT_DIRECTORY_NAME / "unreviewed.json").write_bytes(
                b"{}"
            )

    _mock_replay(
        monkeypatch,
        saved_run,
        action=action,
        complete=kind != "incomplete_replay",
        wrong_manifest=kind == "wrong_replay_manifest",
    )
    with pytest.raises((ReductionError, tasks.GbmapHierarchyTaskDriverError)):
        _reduce(saved_run)


@pytest.mark.parametrize("kind", ["manifest", "checkpoint", "checkpoint_add", "checkpoint_remove"])
def test_run_must_stay_identical_during_pure_reduction(monkeypatch, saved_run, kind):
    reduce = driver.reduce_completed_validation

    def change_after_reduction(*args):
        result = reduce(*args)
        if kind == "manifest":
            document = saved_run.manifest.model_dump(mode="python")
            document["profile_digest"] = core._hash("changed after reduction")
            changed = core._manifest(document)
            (saved_run.directory / tasks.MANIFEST_NAME).write_bytes(
                tasks.canonical_manifest_bytes(_old_manifest(changed))
            )
        elif kind == "checkpoint":
            row = saved_run.rows[0]
            evaluation = row.evaluation.model_dump(mode="python")
            evaluation["mean_per_count_nll"] = 9.0
            evaluation = core._seal(
                evaluation, "evaluation_output_digest", "gbmap-hierarchy-evaluation-output/1.0.0"
            )
            saved_run.paths[0].unlink()
            _write_checkpoint(saved_run.directory, core._checkpoint(row, evaluation=evaluation))
        elif kind == "checkpoint_add":
            (saved_run.directory / tasks.CHECKPOINT_DIRECTORY_NAME / "unreviewed.json").write_bytes(
                b"{}"
            )
        else:
            saved_run.paths[0].unlink()
        return result

    _mock_replay(monkeypatch, saved_run)
    monkeypatch.setattr(driver, "reduce_completed_validation", change_after_reduction)
    with pytest.raises((ReductionError, tasks.GbmapHierarchyTaskDriverError)):
        _reduce(saved_run)


@pytest.mark.parametrize("phase", ["replay", "reduction"])
def test_source_file_change_across_replay_fails_and_guard_is_closed(monkeypatch, saved_run, phase):
    handles = []
    original = driver.fit_driver._open_source_guard

    def guard(snapshot):
        handle = original(snapshot)
        handles.append(handle)
        return handle

    monkeypatch.setattr(driver.fit_driver, "_open_source_guard", guard)
    if phase == "replay":
        _mock_replay(
            monkeypatch, saved_run, action=lambda: saved_run.source.write_bytes(b"changed source")
        )
    else:
        reduce = driver.reduce_completed_validation

        def change_after_reduction(*args):
            result = reduce(*args)
            saved_run.source.write_bytes(b"changed source")
            return result

        monkeypatch.setattr(driver, "reduce_completed_validation", change_after_reduction)
        _mock_replay(monkeypatch, saved_run)
    with pytest.raises(
        driver.fit_driver.GbmapDevelopmentFitDriverError, match="identity or containment changed"
    ):
        _reduce(saved_run)
    assert handles
    assert handles[0].closed


def test_successful_reduction_closes_the_source_guard(monkeypatch, saved_run):
    handles = []
    original = driver.fit_driver._open_source_guard

    def guard(snapshot):
        handle = original(snapshot)
        handles.append(handle)
        return handle

    monkeypatch.setattr(driver.fit_driver, "_open_source_guard", guard)
    _mock_replay(monkeypatch, saved_run)
    _reduce(saved_run)
    assert handles
    assert handles[0].closed


@pytest.mark.parametrize(
    "changes",
    [
        {"verification_kind": "source_replayed_complete_task_reduction"},
        {"source_replay_receipt_digest": core._hash("invented replay")},
    ],
)
def test_planning_bundle_cannot_claim_complete_source_replay(saved_run, changes):
    document = driver.assess_run(saved_run.directory).model_dump(mode="json")
    document.update(changes)
    with pytest.raises((ReductionError, ValidationError), match="scope"):
        driver.ReductionBundle.model_validate_json(canonical_json_bytes(_sealed_bundle(document)))


def test_complete_bundle_cannot_be_relabelled_as_metadata_only(monkeypatch, saved_run):
    _mock_replay(monkeypatch, saved_run)
    document = _reduce(saved_run).model_dump(mode="json")
    document["verification_kind"] = "saved_plan_feasibility"
    with pytest.raises((ReductionError, ValidationError), match="scope"):
        driver.ReductionBundle.model_validate_json(canonical_json_bytes(_sealed_bundle(document)))


def test_complete_bundle_rejects_selection_from_a_different_manifest(saved_run):
    other, rows = core._fixture(whole=4)
    selection = core.reduce_completed_validation(other, rows)
    with pytest.raises((ReductionError, ValidationError), match="inventories"):
        driver._bundle(_old_manifest(saved_run.manifest), selection, core._hash("replay"))


def test_complete_task_evidence_can_abstain_without_becoming_a_fitted_model():
    manifest, rows = core._fixture(whole=2, within=1)
    selection = core.reduce_completed_validation(manifest, rows)
    bundle = driver._bundle(_old_manifest(manifest), selection, core._hash("replay"))
    assert bundle.verification_kind == "source_replayed_complete_task_reduction"
    assert bundle.selection.selected_shrinkage is None
    assert bundle.planning.planning_gate_status == "infeasible_preparation_support"
    assert bundle.selection.final_model_fitted is False
    assert bundle.selection.model_artifact_emitted is False


def test_saved_verification_is_canonical_integrity_only(tmp_path, saved_run):
    bundle = driver.assess_run(saved_run.directory)
    receipt = tmp_path / "private-assessment.json"
    receipt.write_bytes(driver.canonical_bundle_bytes(bundle))
    verified = driver.verify_saved(receipt)
    assert verified == {
        "verified": True,
        "verification_scope": "saved_integrity_not_source_replay",
        "bundle_digest": bundle.bundle_digest,
        "model_fitted": False,
        "model_artifact_emitted": False,
        "runtime_mount_permitted": False,
    }


@pytest.mark.parametrize(
    "kind",
    ["duplicate_json", "indentation", "missing_newline", "seal", "method_drift", "extra_field"],
)
def test_saved_verification_rejects_noncanonical_tampered_or_stale_method(
    tmp_path, monkeypatch, saved_run, kind
):
    bundle = driver.assess_run(saved_run.directory)
    document = bundle.model_dump(mode="json")
    payload = driver.canonical_bundle_bytes(bundle)
    if kind == "duplicate_json":
        payload = payload.replace(
            b'"bundle_digest":', b'"bundle_digest":"sha256:' + b"0" * 64 + b'","bundle_digest":', 1
        )
    elif kind == "indentation":
        payload = json.dumps(document, indent=2).encode() + b"\n"
    elif kind == "missing_newline":
        payload = payload[:-1]
    elif kind == "seal":
        document["bundle_digest"] = core._hash("wrong seal")
        payload = canonical_json_bytes(document) + b"\n"
    elif kind == "extra_field":
        document["unreviewed"] = False
        payload = canonical_json_bytes(_sealed_bundle(document)) + b"\n"
    else:
        monkeypatch.setattr(driver, "method_digest", lambda: core._hash("changed method"))
    receipt = tmp_path / "private-tampered.json"
    receipt.write_bytes(payload)
    with pytest.raises((ReductionError, ValidationError)):
        driver.verify_saved(receipt)


def test_canonical_export_revalidates_models_and_output_bound(monkeypatch, saved_run):
    bundle = driver.assess_run(saved_run.directory)
    forged = bundle.model_copy(update={"bundle_digest": core._hash("wrong")})
    with pytest.raises((ReductionError, ValidationError)):
        driver.canonical_bundle_bytes(forged)
    monkeypatch.setattr(driver, "_MAX_BYTES", 1)
    with pytest.raises(ReductionError, match="output bound"):
        driver.canonical_bundle_bytes(bundle)


def test_method_digest_binds_current_code_profile_and_normalizes_crlf(monkeypatch):
    root = Path("synthetic-method-root")
    monkeypatch.setattr(driver, "_ROOT", root)
    monkeypatch.setattr(
        driver, "development_profile", lambda: SimpleNamespace(profile_digest=core._hash("profile"))
    )
    calls = []
    current = [b"module_code\r\n"]

    def read(path, _maximum, _message):
        calls.append(path)
        return current[0]

    monkeypatch.setattr(tasks, "_read_regular_bytes", read)
    first = driver.method_digest()
    assert len(calls) == 5
    assert any(path.name == "reduce_gbmap_hierarchy_tasks.py" for path in calls)
    assert any(path.name == "run_gbmap_hierarchy_tasks.py" for path in calls)
    current[0] = b"module_code\n"
    assert driver.method_digest() == first
    current[0] = b"different_code\n"
    assert driver.method_digest() != first
    current[0] = b"module_code\n"
    monkeypatch.setattr(
        driver,
        "development_profile",
        lambda: SimpleNamespace(profile_digest=core._hash("different profile")),
    )
    assert driver.method_digest() != first


def test_cli_assess_and_verify_publish_only_scoped_private_receipts(tmp_path, saved_run, capsys):
    output = tmp_path / "assessment.json"
    argv = ["assess", str(saved_run.directory), "--output", str(output)]
    assert driver.main(argv) == 0
    first = capsys.readouterr()
    assert first.err == ""
    assert first.out.encode() == output.read_bytes()
    assert json.loads(first.out)["verification_kind"] == "saved_plan_feasibility"
    assert driver.main(argv) == 0
    assert capsys.readouterr().out == first.out
    assert driver.main(["verify", str(output)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["verification_scope"] == "saved_integrity_not_source_replay"


def test_cli_reduce_forwards_mandatory_acknowledgements_and_saves_complete_bundle(
    tmp_path, monkeypatch, saved_run, capsys
):
    _mock_replay(monkeypatch, saved_run)
    output = tmp_path / "complete-reduction.json"
    args = [
        "reduce",
        str(saved_run.directory),
        "--source",
        str(saved_run.source),
        "--reviewed-sha256",
        saved_run.manifest.reviewed_sha256,
        "--preflight",
        str(saved_run.preflight),
        "--acknowledge-development-only",
        "--acknowledge-sha256-independently-reviewed",
        "--output",
        str(output),
    ]
    assert driver.main(args) == 0
    result = capsys.readouterr()
    assert result.err == ""
    assert result.out.encode() == output.read_bytes()
    assert json.loads(result.out)["verification_kind"] == "source_replayed_complete_task_reduction"
    assert driver.verify_saved(output)["verification_scope"] == "saved_integrity_not_source_replay"


@pytest.mark.parametrize("kind", ["inside_run", "existing_different", "repository"])
def test_cli_refuses_unsafe_output_and_does_not_overwrite(tmp_path, saved_run, capsys, kind):
    original = b"existing private bytes"
    if kind == "inside_run":
        destination = saved_run.directory / "reduction.json"
    elif kind == "repository":
        destination = driver._ROOT / "reduction-must-not-be-created.json"
        assert not destination.exists()
    else:
        destination = tmp_path / "existing.json"
        destination.write_bytes(original)
    assert driver.main(["assess", str(saved_run.directory), "--output", str(destination)]) == 1
    result = capsys.readouterr()
    assert result.out == ""
    assert result.err == "error: GBmap validation reduction failed closed\n"
    if kind == "existing_different":
        assert destination.read_bytes() == original
    else:
        assert not destination.exists()


@pytest.mark.parametrize("command", ["assess", "verify", "reduce"])
def test_cli_sanitizes_private_paths_and_nested_errors(monkeypatch, capsys, command):
    target = "secret-patient-identifying-path"

    def fail(*_args, **_kwargs):
        raise OSError(target)

    method = {"assess": "assess_run", "verify": "verify_saved", "reduce": "reduce_run"}[command]
    monkeypatch.setattr(driver, method, fail)
    args = [command, target]
    if command == "reduce":
        args += [
            "--source",
            target,
            "--reviewed-sha256",
            target,
            "--preflight",
            target,
            "--acknowledge-development-only",
            "--acknowledge-sha256-independently-reviewed",
        ]
    assert driver.main(args) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "error: GBmap validation reduction failed closed\n"
    assert target not in output.err


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["unknown-secret-command"],
        ["reduce", "private-run"],
        ["assess", "private-run", "--secret-unsupported"],
    ],
)
def test_cli_argument_errors_do_not_echo_private_material(capsys, args):
    with pytest.raises(SystemExit) as error:
        driver.main(args)
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "error: validation reduction arguments were not accepted\n"


@pytest.mark.parametrize("kind", ["missing_directory", "missing_manifest"])
def test_existing_private_run_and_manifest_are_required(tmp_path, kind):
    directory = tmp_path / "absent-private-run"
    if kind == "missing_manifest":
        directory.mkdir()
    with pytest.raises(ReductionError):
        driver.assess_run(directory)

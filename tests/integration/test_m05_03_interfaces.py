"""Black-box schema, CLI, filesystem, and parity checks for M05-03."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import IO, Any, Final, cast
from unittest.mock import MagicMock

import pytest
from evals.m05_03.run import build_scenario
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import cli as cli_module
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m05_03 import (
    M0503_MAX_CANONICAL_REQUEST_BYTES,
    PtmLocalizationRawInputValidationResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_03_raw_ingestion import (
    M0503Plugin,
    M0503Service,
    M0503Submission,
    ingest_ptm_localization_raw_inputs,
)

pytestmark = pytest.mark.integration

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "policy",
    "parser-profile",
    "input-artifact",
    "proteome-document",
    "genome-document",
    "transcriptome-document",
    "ptm-document",
    "validated-input",
    "diagnostic",
    "receipt",
)
SOURCE_FILENAMES: Final = (
    "mass-spectrometry-proteome.json",
    "genome.json",
    "transcriptome.json",
    "ptm-annotations.json",
)
HTTP_OK: Final = 200
HTTP_NOT_FOUND: Final = 404
CLI_USAGE_ERROR: Final = 2
DENIED_CONTROL_STATES: Final = (
    ("approved_configuration", "rejected"),
    ("identity_lineage", "unresolved"),
    ("provenance", "rejected"),
    ("consent", "denied"),
    ("quality", "rejected"),
    ("support", "rejected"),
    ("intended_use", "rejected"),
)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m05_03_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M05-03/{name}/schema")
        absent = client.post("/v1/modules/M05-03/raw-ingestion", json={})
    cli = CliRunner().invoke(cli_app, ["ptm-localization-raw", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert absent.status_code == HTTP_NOT_FOUND
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$id"].endswith(f":{name}")


def _write_capsule(root: Path) -> tuple[Path, Path, Path, PtmLocalizationRawInputValidationResult]:
    scenario = build_scenario()
    request_path = root / "request.json"
    source_directory = root / "source"
    output_path = root / "result.json"
    source_directory.mkdir()
    request_path.write_bytes(canonical_json_bytes(scenario.request.model_dump(mode="json")))
    for filename, role in zip(SOURCE_FILENAMES, scenario.artifacts_by_role, strict=True):
        (source_directory / filename).write_bytes(scenario.artifacts_by_role[role])
    expected = ingest_ptm_localization_raw_inputs(scenario.request, scenario.artifacts_by_role)
    return request_path, source_directory, output_path, expected


def test_library_service_plugin_and_cli_emit_exact_parity(tmp_path: Path) -> None:
    request_path, source_directory, output_path, expected = _write_capsule(tmp_path)
    scenario = build_scenario()
    service = M0503Service()
    plugin = M0503Plugin(service)
    token = plugin.validate(M0503Submission(scenario.request, scenario.artifacts_by_role))

    cli = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(source_directory),
            "--output",
            str(output_path),
        ],
    )

    assert cli.exit_code == 0, cli.output
    cli_result = PtmLocalizationRawInputValidationResult.model_validate_json(
        output_path.read_bytes(), strict=True
    )
    assert expected == service.execute(scenario.request, scenario.artifacts_by_role)
    assert expected == plugin.run(token) == cli_result
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M05-03"


def test_cli_rejects_missing_extra_linked_and_existing_output(tmp_path: Path) -> None:
    request_path, source_directory, output_path, _ = _write_capsule(tmp_path)
    (source_directory / SOURCE_FILENAMES[0]).unlink()
    missing = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(source_directory),
            "--output",
            str(output_path),
        ],
    )
    assert missing.exit_code == 1

    scenario = build_scenario()
    (source_directory / SOURCE_FILENAMES[0]).write_bytes(
        scenario.artifacts_by_role[next(iter(scenario.artifacts_by_role))]
    )
    (source_directory / "extra.json").write_bytes(b"{}")
    extra = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(source_directory),
            "--output",
            str(output_path),
        ],
    )
    assert extra.exit_code == 1
    (source_directory / "extra.json").unlink()

    output_path.write_bytes(b"existing")
    existing = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(source_directory),
            "--output",
            str(output_path),
        ],
    )
    assert existing.exit_code == 1
    assert output_path.read_bytes() == b"existing"


def test_cli_rejects_symlinked_source_when_supported(tmp_path: Path) -> None:
    request_path, source_directory, output_path, _ = _write_capsule(tmp_path)
    target = source_directory / SOURCE_FILENAMES[0]
    replacement = source_directory / "replacement.json"
    target.replace(replacement)
    try:
        target.symlink_to(replacement)
    except OSError as error:
        pytest.skip(f"platform cannot create a test symlink: {error}")

    result = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(source_directory),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 1
    assert (
        "link or reparse point" in result.output or "exactly four locked filenames" in result.output
    )
    assert not output_path.exists()


@pytest.mark.parametrize("mutation", ["duplicate", "unknown", "coercion"])
def test_cli_rejects_non_strict_request_json(
    tmp_path: Path,
    mutation: str,
) -> None:
    request_path, source_directory, output_path, _ = _write_capsule(tmp_path)
    if mutation == "duplicate":
        serialized = request_path.read_text(encoding="utf-8").replace(
            '"operation":"ingest_ptm_localization_raw_inputs"',
            (
                '"operation":"ingest_ptm_localization_raw_inputs",'
                '"operation":"ingest_ptm_localization_raw_inputs"'
            ),
            1,
        )
    else:
        payload = json.loads(request_path.read_bytes())
        if mutation == "unknown":
            payload["unexpected"] = "rejected"
        else:
            payload["contract_version"] = 1
        serialized = json.dumps(payload)
    request_path.write_text(serialized, encoding="utf-8")

    result = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(source_directory),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == CLI_USAGE_ERROR
    assert "Traceback" not in result.output
    assert not output_path.exists()


def test_cli_accepts_exact_four_mib_request_and_rejects_plus_one_before_source(
    tmp_path: Path,
) -> None:
    request_path, source_directory, output_path, expected = _write_capsule(tmp_path)
    serialized = request_path.read_bytes()
    exact = serialized + (b" " * (M0503_MAX_CANONICAL_REQUEST_BYTES - len(serialized)))
    assert len(exact) == M0503_MAX_CANONICAL_REQUEST_BYTES
    request_path.write_bytes(exact)

    accepted = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(source_directory),
            "--output",
            str(output_path),
        ],
    )
    assert accepted.exit_code == 0, accepted.output
    assert (
        PtmLocalizationRawInputValidationResult.model_validate_json(
            output_path.read_bytes(), strict=True
        )
        == expected
    )

    output_path.unlink()
    request_path.write_bytes(exact + b" ")
    hostile_source = tmp_path / "must-not-be-read"
    hostile_source.write_bytes(b"source traversal would expose this non-directory")
    rejected = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(hostile_source),
            "--output",
            str(output_path),
        ],
    )
    assert rejected.exit_code == CLI_USAGE_ERROR
    assert "byte limit" in rejected.output
    assert "is a file" not in rejected.output
    assert not output_path.exists()


@pytest.mark.parametrize(("control", "state"), DENIED_CONTROL_STATES)
def test_cli_authorization_denial_precedes_source_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    control: str,
    state: str,
) -> None:
    request_path, _source_directory, output_path, _ = _write_capsule(tmp_path)
    payload = json.loads(request_path.read_bytes())
    payload["context"]["references"][control]["state"] = state
    request_path.write_bytes(canonical_json_bytes(payload))
    hostile_source = tmp_path / "must-not-be-classified"
    hostile_source.write_bytes(b"an existing regular file is not a source directory")
    output_path.write_bytes(b"an existing output must not be inspected before authorization")
    original_stat = os.stat
    governed_paths = {hostile_source, output_path}
    touched: list[Path] = []

    def tracking_stat(path: object, *args: object, **kwargs: object) -> os.stat_result:
        try:
            candidate = Path(cast("str | os.PathLike[str]", path))
        except TypeError:
            candidate = None
        if candidate in governed_paths:
            touched.append(candidate)
        return original_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "stat", tracking_stat)

    result = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(hostile_source),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == CLI_USAGE_ERROR
    assert result.output.startswith("PTM-localization raw ingestion failed:")
    assert "is a file" not in result.output
    assert "source directory" not in result.output
    assert touched == []
    assert output_path.read_bytes().startswith(b"an existing output")


def test_cli_source_reads_are_bounded_and_size_caps_precede_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = build_scenario()
    source_directory = tmp_path / "source"
    source_directory.mkdir()
    for filename, role in zip(SOURCE_FILENAMES, scenario.artifacts_by_role, strict=True):
        (source_directory / filename).write_bytes(scenario.artifacts_by_role[role])

    original_open = Path.open
    read_limits: list[int] = []

    def guarded_open(  # noqa: PLR0913, PLR0917 - mirrors Path.open exactly.
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[Any]:
        stream = original_open(path, mode, buffering, encoding, errors, newline)
        if mode != "rb" or path.parent != source_directory:
            return stream
        wrapper = MagicMock(wraps=stream)
        wrapper.__enter__.return_value = wrapper
        wrapper.__exit__.side_effect = stream.__exit__
        wrapper.fileno.side_effect = stream.fileno

        def bounded_read(size: int = -1) -> bytes:
            assert size >= 0
            read_limits.append(size)
            return cast("bytes", stream.read(size))

        wrapper.read.side_effect = bounded_read
        return wrapper

    monkeypatch.setattr(Path, "open", guarded_open)
    snapshots = cli_module._load_ptm_localization_raw_files(source_directory, scenario.request)
    assert snapshots == scenario.artifacts_by_role
    assert read_limits == [
        (source_directory / filename).stat().st_size + 1 for filename in SOURCE_FILENAMES
    ]

    oversized = source_directory / SOURCE_FILENAMES[0]
    with original_open(oversized, "ab") as stream:
        stream.write(b"x")
    read_limits.clear()
    with pytest.raises(ValueError, match="source is unavailable"):
        cli_module._load_ptm_localization_raw_files(source_directory, scenario.request)
    assert read_limits == []


def test_cli_rejects_linked_source_ancestor_when_supported(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    request_path, source_directory, output_path, _ = _write_capsule(real_root)
    linked_root = tmp_path / "linked"
    try:
        linked_root.symlink_to(real_root, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"platform cannot create a directory symlink: {error}")

    result = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(linked_root / source_directory.name),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 1
    assert "link or reparse point" in result.output
    assert not output_path.exists()


def test_cli_rejects_inventory_change_during_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = build_scenario()
    source_directory = tmp_path / "source"
    source_directory.mkdir()
    for filename, role in zip(SOURCE_FILENAMES, scenario.artifacts_by_role, strict=True):
        (source_directory / filename).write_bytes(scenario.artifacts_by_role[role])

    original_open = Path.open
    inventory_changed = False

    def changing_open(  # noqa: PLR0913, PLR0917 - mirrors Path.open exactly.
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[Any]:
        stream = original_open(path, mode, buffering, encoding, errors, newline)
        if mode != "rb" or path.name != SOURCE_FILENAMES[0]:
            return stream
        wrapper = MagicMock(wraps=stream)
        wrapper.__enter__.return_value = wrapper
        wrapper.__exit__.side_effect = stream.__exit__
        wrapper.fileno.side_effect = stream.fileno

        def read_then_change(size: int = -1) -> bytes:
            nonlocal inventory_changed
            payload = cast("bytes", stream.read(size))
            if not inventory_changed:
                inventory_changed = True
                with original_open(source_directory / "extra.json", "wb") as extra:
                    extra.write(b"{}")
            return payload

        wrapper.read.side_effect = read_then_change
        return wrapper

    monkeypatch.setattr(Path, "open", changing_open)
    with pytest.raises(ValueError, match="changed during ingestion"):
        cli_module._load_ptm_localization_raw_files(source_directory, scenario.request)
    assert inventory_changed is True


def test_cli_atomic_output_rejects_parent_reparse_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_parent = tmp_path / "output"
    output_parent.mkdir()
    escape = tmp_path / "escape"
    escape.mkdir()
    probe = tmp_path / "link-probe"
    try:
        probe.symlink_to(escape, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"platform cannot create a directory symlink: {error}")
    probe.unlink()

    displaced_parent = tmp_path / "output-before-swap"
    output_path = output_parent / "result.json"
    publication_succeeded = False

    def swap_parent() -> None:
        output_parent.rename(displaced_parent)
        output_parent.symlink_to(escape, target_is_directory=True)

    if os.name == "nt":
        original_rename = cli_module._windows_rename_ptm_localization_raw_output

        def swapping_rename(
            output_handle: int,
            parent_handle: int,
            final_name: str,
        ) -> None:
            nonlocal publication_succeeded
            swap_parent()
            original_rename(output_handle, parent_handle, final_name)
            publication_succeeded = True

        monkeypatch.setattr(
            cli_module,
            "_windows_rename_ptm_localization_raw_output",
            swapping_rename,
        )
    else:
        original_link = os.link

        def swapping_link(
            source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            **kwargs: Any,
        ) -> None:
            nonlocal publication_succeeded
            swap_parent()
            original_link(source, destination, **kwargs)
            publication_succeeded = True

        monkeypatch.setattr(os, "link", swapping_link)

    with pytest.raises(ValueError, match="new regular file"):
        cli_module._write_ptm_localization_raw_result(output_path, b"must-not-escape")

    assert publication_succeeded is (os.name != "nt")
    assert not (escape / output_path.name).exists()
    assert tuple(escape.glob(".m0503-*.tmp")) == ()
    received_parent = output_parent if os.name == "nt" else displaced_parent
    assert received_parent.is_dir()
    assert not (received_parent / output_path.name).exists()
    assert tuple(received_parent.glob(".m0503-*.tmp")) == ()


def test_cli_atomic_output_cleans_transient_parent_swap(  # noqa: PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_parent = tmp_path / "output"
    output_parent.mkdir()
    escape = tmp_path / "escape"
    escape.mkdir()
    probe = tmp_path / "link-probe"
    try:
        probe.symlink_to(escape, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"platform cannot create a directory symlink: {error}")
    probe.unlink()

    displaced_parent = tmp_path / "output-before-swap"
    output_path = output_parent / "result.json"
    publication_succeeded = False

    def swap_parent() -> None:
        output_parent.rename(displaced_parent)
        output_parent.symlink_to(escape, target_is_directory=True)

    def restore_parent() -> None:
        output_parent.unlink()
        displaced_parent.rename(output_parent)

    if os.name == "nt":
        original_rename = cli_module._windows_rename_ptm_localization_raw_output

        def transient_rename(
            output_handle: int,
            parent_handle: int,
            final_name: str,
        ) -> None:
            nonlocal publication_succeeded
            swap_parent()
            try:
                original_rename(output_handle, parent_handle, final_name)
                publication_succeeded = True
                cli_module._raise_anchored_output_error()
            finally:
                restore_parent()

        monkeypatch.setattr(
            cli_module,
            "_windows_rename_ptm_localization_raw_output",
            transient_rename,
        )
    else:
        original_link = os.link

        def transient_link(
            source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            **kwargs: Any,
        ) -> None:
            nonlocal publication_succeeded
            swap_parent()
            try:
                original_link(source, destination, **kwargs)
                publication_succeeded = True
                cli_module._raise_anchored_output_error()
            finally:
                restore_parent()

        monkeypatch.setattr(os, "link", transient_link)

    with pytest.raises(ValueError, match="new regular file"):
        cli_module._write_ptm_localization_raw_result(output_path, b"must-not-escape")

    assert publication_succeeded is (os.name != "nt")
    assert not output_path.exists()
    assert not (escape / output_path.name).exists()
    assert tuple(escape.glob(".m0503-*.tmp")) == ()
    assert tuple(output_parent.glob(".m0503-*.tmp")) == ()
    assert not displaced_parent.exists()


def test_cli_atomic_output_rolls_back_late_publication_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_parent = tmp_path / "output"
    output_parent.mkdir()
    output_path = output_parent / "result.json"
    publication_succeeded = False

    if os.name == "nt":
        original_rename = cli_module._windows_rename_ptm_localization_raw_output

        def failing_rename(
            output_handle: int,
            parent_handle: int,
            final_name: str,
        ) -> None:
            nonlocal publication_succeeded
            original_rename(output_handle, parent_handle, final_name)
            publication_succeeded = True
            cli_module._raise_anchored_output_error()

        monkeypatch.setattr(
            cli_module,
            "_windows_rename_ptm_localization_raw_output",
            failing_rename,
        )
    else:
        original_link = os.link

        def failing_link(
            source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            **kwargs: Any,
        ) -> None:
            nonlocal publication_succeeded
            original_link(source, destination, **kwargs)
            publication_succeeded = True
            cli_module._raise_anchored_output_error()

        monkeypatch.setattr(os, "link", failing_link)

    with pytest.raises(ValueError, match="new regular file"):
        cli_module._write_ptm_localization_raw_result(output_path, b"must-be-rolled-back")

    assert publication_succeeded is True
    assert not output_path.exists()
    assert tuple(output_parent.glob(".m0503-*.tmp")) == ()


def test_cli_rejects_replaced_earlier_member_even_if_root_time_is_restored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = build_scenario()
    source_directory = tmp_path / "source"
    source_directory.mkdir()
    for filename, role in zip(SOURCE_FILENAMES, scenario.artifacts_by_role, strict=True):
        (source_directory / filename).write_bytes(scenario.artifacts_by_role[role])

    first = source_directory / SOURCE_FILENAMES[0]
    second = source_directory / SOURCE_FILENAMES[1]
    root_receipt = source_directory.stat()
    original_open = Path.open
    member_replaced = False

    def replacing_open(  # noqa: PLR0913, PLR0917 - mirrors Path.open exactly.
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[Any]:
        nonlocal member_replaced
        if path == second and mode == "rb" and not member_replaced:
            member_replaced = True
            replacement = source_directory / "replacement.tmp"
            with original_open(replacement, "wb") as stream:
                stream.write(b"x" * first.stat().st_size)
            replacement.replace(first)
            os.utime(
                source_directory,
                ns=(root_receipt.st_atime_ns, root_receipt.st_mtime_ns),
            )
        return original_open(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", replacing_open)
    with pytest.raises(ValueError, match="changed during ingestion"):
        cli_module._load_ptm_localization_raw_files(source_directory, scenario.request)
    assert member_replaced is True


def test_cli_rejects_nonregular_member_and_symlink_output_when_supported(
    tmp_path: Path,
) -> None:
    request_path, source_directory, output_path, _ = _write_capsule(tmp_path)
    member = source_directory / SOURCE_FILENAMES[0]
    member.unlink()
    member.mkdir()
    nonregular = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(source_directory),
            "--output",
            str(output_path),
        ],
    )
    assert nonregular.exit_code == 1
    assert not output_path.exists()

    member.rmdir()
    scenario = build_scenario()
    member.write_bytes(scenario.artifacts_by_role[next(iter(scenario.artifacts_by_role))])
    target = tmp_path / "linked-output-target.json"
    try:
        output_path.symlink_to(target)
    except OSError as error:
        pytest.skip(f"platform cannot create a test symlink: {error}")
    linked_output = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-raw",
            "ingest",
            str(request_path),
            str(source_directory),
            "--output",
            str(output_path),
        ],
    )
    assert linked_output.exit_code == 1
    assert not target.exists()

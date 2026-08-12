"""Black-box checks for the thin M02-03 schema and file-backed CLI surfaces."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m02_03 import (
    IdentificationRawIngestionResult,
    IngestIdentificationRawInputsRequest,
    RawInputDisposition,
)
from glio_proteogen.modules.c02_identification_qc.m02_03_raw_ingestion import M0203Service
from tests.modules.c02_identification_qc.test_m02_03_engine import _request

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
HTTP_OK: Final = 200
HTTP_NOT_FOUND: Final = 404
SCHEMAS = (
    "request",
    "output",
    "policy",
    "source",
    "role_requirement",
    "bundle_diagnostic",
)


@pytest.mark.parametrize("name", SCHEMAS)
def test_api_and_cli_export_identical_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M02-03/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["identification-raw", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["x-glio-contract"]["rawPayloadInSchema"] is False


def test_api_does_not_expose_raw_bytes_through_json(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "schema-only.sqlite3")) as client:
        response = client.post("/v1/modules/M02-03/ingest", json={})

    assert response.status_code == HTTP_NOT_FOUND


def test_cli_ingests_exact_declared_files_and_matches_library(tmp_path: Path) -> None:
    request, payloads = _request()
    source_directory = tmp_path / "sources"
    source_directory.mkdir()
    filenames: dict[str, str] = {}
    for source_id, payload in payloads.items():
        (source_directory / source_id).write_bytes(payload)
        filenames[source_id] = source_id
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")

    cli = CliRunner().invoke(
        cli_app,
        ["identification-raw", "ingest", str(request_path), str(source_directory)],
    )

    assert cli.exit_code == 0, cli.output
    result = IdentificationRawIngestionResult.model_validate_json(cli.stdout, strict=True)
    assert result == M0203Service().execute(request, payloads, filenames)
    assert result.disposition is RawInputDisposition.ACCEPTED


def test_cli_bounds_each_file_at_declared_size_without_echoing_content(tmp_path: Path) -> None:
    request, payloads = _request()
    source_directory = tmp_path / "sources"
    source_directory.mkdir()
    for source_id, payload in payloads.items():
        (source_directory / source_id).write_bytes(payload)
    source_id = request.sources[0].source.source_id
    canary = b"private-patient-canary"
    (source_directory / source_id).write_bytes(payloads[source_id] + canary)
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")

    cli = CliRunner().invoke(
        cli_app,
        ["identification-raw", "ingest", str(request_path), str(source_directory)],
    )

    assert cli.exit_code == 1
    assert "raw source size contradicts its declaration" in cli.output
    assert canary.decode() not in cli.output


def test_cli_rejects_symlinked_source_without_reading_target(tmp_path: Path) -> None:
    request, payloads = _request()
    source_directory = tmp_path / "sources"
    source_directory.mkdir()
    source_id = request.sources[0].source.source_id
    target = tmp_path / "outside.bin"
    target.write_bytes(payloads[source_id])
    try:
        (source_directory / source_id).symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    for other_id, payload in payloads.items():
        if other_id != source_id:
            (source_directory / other_id).write_bytes(payload)
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")

    cli = CliRunner().invoke(
        cli_app,
        ["identification-raw", "ingest", str(request_path), str(source_directory)],
    )

    assert cli.exit_code == 1
    assert "raw source cannot traverse a symbolic link" in cli.output
    assert "outside.bin" not in cli.output


def test_cli_rejects_nonportable_source_identifier_before_file_access(tmp_path: Path) -> None:
    request, _ = _request()
    first = request.sources[0]
    unsafe_source = first.source.model_copy(update={"source_id": "C:escape"})
    unsafe_request = IngestIdentificationRawInputsRequest(
        context=request.context,
        policy=request.policy,
        sources=(first.model_copy(update={"source": unsafe_source}), *request.sources[1:]),
    )
    source_directory = tmp_path / "sources"
    source_directory.mkdir()
    request_path = tmp_path / "request.json"
    request_path.write_text(unsafe_request.model_dump_json(), encoding="utf-8")

    cli = CliRunner().invoke(
        cli_app,
        ["identification-raw", "ingest", str(request_path), str(source_directory)],
    )

    assert cli.exit_code == 1
    assert "raw source identifier is not a safe filename" in cli.output

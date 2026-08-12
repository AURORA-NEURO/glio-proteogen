"""Black-box checks for the intentionally thin M01-03 transport surfaces."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m01_03.v1 import ValidatedRawInputDescriptor

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parents[1] / "fixtures" / "m01_03"
SCHEMA_NAMES = ("request", "output", "policy", "source", "raw_input", "diagnostic")
HTTP_OK = 200
HTTP_UNSUPPORTED_MEDIA_TYPE = 415
HTTP_UNPROCESSABLE_CONTENT = 422
CLI_INVALID_INPUT = 2


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_the_same_schema(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M01-03/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["raw", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_binary_api_and_cli_emit_equivalent_metadata(tmp_path: Path) -> None:
    source = FIXTURES / "variants.valid.vcf"
    body = source.read_bytes()
    with TestClient(create_app(tmp_path / "inspect.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-03/inspect",
            params={"source_id": "source.interfaces", "filename": source.name},
            content=body,
            headers={"content-type": "application/octet-stream"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["raw", "inspect", str(source), "--source-id", "source.interfaces"],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    parsed = TypeAdapter(ValidatedRawInputDescriptor).validate_json(response.content, strict=True)
    assert parsed.detected is not None
    assert parsed.detected.format.value == "VCF"


def test_binary_api_requires_media_type_and_valid_identifier(tmp_path: Path) -> None:
    body = (FIXTURES / "variants.valid.vcf").read_bytes()
    with TestClient(create_app(tmp_path / "invalid.sqlite3")) as client:
        media = client.post(
            "/v1/modules/M01-03/inspect?source_id=source.valid",
            content=body,
            headers={"content-type": "text/plain"},
        )
        identifier = client.post(
            "/v1/modules/M01-03/inspect?source_id=contains%20space",
            content=body,
            headers={"content-type": "application/octet-stream"},
        )

    assert media.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert identifier.status_code == HTTP_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    "parameters",
    [
        {"source_id": "source.valid", "filename": "x" * 513},
        {"source_id": "source.valid", "expected_sha256": "0" * 81},
    ],
)
def test_binary_api_bounds_advisory_text(
    tmp_path: Path,
    parameters: dict[str, str],
) -> None:
    body = (FIXTURES / "variants.valid.vcf").read_bytes()
    with TestClient(create_app(tmp_path / "advisory-bounds.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-03/inspect",
            params=parameters,
            content=body,
            headers={"content-type": "application/octet-stream"},
        )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_cli_rejects_invalid_source_identifier_without_reading_content(tmp_path: Path) -> None:
    canary = "patient-jane-sensitive-canary"
    source = tmp_path / "valid.fasta"
    source.write_text(f">synthetic\n{canary}\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli_app,
        ["raw", "inspect", str(source), "--source-id", "contains space"],
    )

    assert result.exit_code == CLI_INVALID_INPUT
    assert canary not in result.output
    assert "invalid source identifier" in result.output


def test_cli_failure_is_typed_and_does_not_echo_content(tmp_path: Path) -> None:
    canary = "patient-jane-sensitive-canary"
    source = tmp_path / "unknown.bin"
    source.write_text(canary, encoding="utf-8")

    result = CliRunner().invoke(
        cli_app,
        ["raw", "inspect", str(source), "--source-id", "source.unknown"],
    )

    assert result.exit_code == 1
    assert canary not in result.output
    assert "unsupported_format" in result.output

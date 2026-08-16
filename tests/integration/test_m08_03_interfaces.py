"""FastAPI and Typer parity tests for M08-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from evals.m08_03.fixtures import request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app
from glio_proteogen.contracts.m08_03 import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_UNSUPPORTED_MEDIA_TYPE = 415
CLI_VALIDATION_ERROR = 2


def test_api_schema_and_estimate_parity(tmp_path: Path) -> None:
    candidate = request()
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        schema = client.get("/v1/contracts/M08-03/request/schema")
        response = client.post(
            "/v1/modules/M08-03/baseline-estimate",
            content=canonical_json_bytes(candidate.model_dump(mode="json")),
            headers={"content-type": "application/json"},
        )
    assert schema.status_code == HTTP_OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert response.status_code == HTTP_OK
    assert response.json()["request_digest"] == canonical_request_digest(candidate)


def test_api_rejects_wrong_media_type(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        response = client.post(
            "/v1/modules/M08-03/baseline-estimate",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
    assert response.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE


def test_cli_schema_and_estimate_are_canonical(tmp_path: Path) -> None:
    candidate = request()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(candidate.model_dump(mode="json")))
    runner = CliRunner()
    schema = runner.invoke(app, ["protein-subtype-baseline", "export-schema", "request"])
    result = runner.invoke(
        app,
        [
            "protein-subtype-baseline",
            "estimate",
            str(request_path),
            "--output",
            str(output_path),
        ],
    )
    assert schema.exit_code == 0, schema.stdout
    assert result.exit_code == 0, result.stdout
    assert output_path.read_bytes() == canonical_json_bytes(json.loads(output_path.read_text()))


def test_cli_duplicate_key_is_rejected(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text('{"request_id":"x","request_id":"y"}')
    result = CliRunner().invoke(
        app,
        [
            "protein-subtype-baseline",
            "estimate",
            str(request_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == CLI_VALIDATION_ERROR
    assert not output_path.exists()

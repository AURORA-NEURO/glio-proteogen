"""API/CLI parity and sanitized boundary tests for M27-05."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from evals.m27_05.fixture import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c27_complex_activity.m27_05_observability_telemetry.api import (
    create_app,
)
from glio_proteogen.modules.c27_complex_activity.m27_05_observability_telemetry.cli import app

_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422
_SCHEMA_COUNT = 8


def test_api_schema_and_emit_parity() -> None:
    request = build_request()
    client = TestClient(create_app())
    schemas = client.get("/v1/modules/M27-05/schemas")
    assert schemas.status_code == _HTTP_OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    emitted = client.post(
        "/v1/modules/M27-05/emit",
        content=request.model_dump_json(),
        headers={"content-type": "application/json"},
    )
    assert emitted.status_code == _HTTP_OK
    assert emitted.json()["status"] == "abstained"


def test_api_rejects_malformed_json_without_private_detail() -> None:
    response = TestClient(create_app()).post(
        "/v1/modules/M27-05/emit",
        content=b"{not-json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text


def test_cli_export_and_emit(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(request_json := build_request().model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(app, ["emit", str(request_path), "--output", str(output_path)])
    assert result.exit_code == 1, result.output
    document = json.loads(output_path.read_text(encoding="utf-8"))
    assert document["status"] == "abstained"
    assert request_json


def test_cli_refuses_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    output_path.write_text("existing", encoding="utf-8")
    result = CliRunner().invoke(app, ["emit", str(request_path), "--output", str(output_path)])
    assert result.exit_code != 0
    assert "overwrite" in result.output.lower()

"""FastAPI, SDK, Typer, and strict-plugin parity tests for M26-07."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m26_07 import M2607_MAX_CANONICAL_REQUEST_BYTES
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback import (
    M2607ChangeControlService,
    M2607Client,
    app,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_07_change_control_rollback.cli import (
    app as cli_app,
)
from tests.runtime.test_m2607_runtime import _request

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_UNPROCESSABLE = 422
HTTP_NOT_FOUND = 404
HTTP_PAYLOAD_TOO_LARGE = 413
HTTP_UNSUPPORTED_MEDIA_TYPE = 415
SCHEMA_COUNT = 8


def test_fastapi_schema_validate_control_and_verify_routes() -> None:
    request = _request()
    body = request.model_dump_json()

    with TestClient(app) as client:
        schemas = client.get("/v1/modules/M26-07/schemas")
        headers = {"content-type": "application/json"}
        validated = client.post("/v1/modules/M26-07/validate", content=body, headers=headers)
        controlled = client.post("/v1/modules/M26-07/control", content=body, headers=headers)
        verified = client.post(
            "/v1/modules/M26-07/verify",
            content=canonical_json_bytes(
                {"request": request.model_dump(mode="json"), "result": controlled.json()}
            ),
            headers=headers,
        )
        forged = request.model_copy(update={"request_id": "request.m2607.forged"})
        mismatch = client.post(
            "/v1/modules/M26-07/verify",
            json={"request": forged.model_dump(mode="json"), "result": controlled.json()},
        )

    assert schemas.status_code == HTTP_OK
    assert len(schemas.json()) == SCHEMA_COUNT
    assert validated.status_code == HTTP_OK
    assert controlled.status_code == HTTP_OK
    assert controlled.json()["status"] == "approved"
    assert verified.status_code == HTTP_OK
    assert verified.json()["verified"] is True
    assert mismatch.status_code == HTTP_UNPROCESSABLE


def test_fastapi_rejects_duplicate_keys_and_unknown_schema() -> None:
    with TestClient(app) as client:
        duplicate = client.post(
            "/v1/modules/M26-07/validate",
            content=b'{"request_id":"a","request_id":"b"}',
            headers={"content-type": "application/json"},
        )
        unknown = client.get("/v1/modules/M26-07/schemas/unknown")

    assert duplicate.status_code == HTTP_UNPROCESSABLE
    assert "strict" not in duplicate.text.lower()
    assert unknown.status_code == HTTP_NOT_FOUND


def test_fastapi_request_ceiling_applies_before_control_parsing() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/modules/M26-07/control",
            content=b"{" + b"x" * M2607_MAX_CANONICAL_REQUEST_BYTES + b"}",
            headers={"content-type": "application/json"},
        )
    assert response.status_code == HTTP_PAYLOAD_TOO_LARGE


def test_fastapi_rejects_unsupported_replay_content_type() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/modules/M26-07/verify",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
    assert response.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE


def test_sdk_preserves_service_canonical_result() -> None:
    request = _request()
    service_result = M2607ChangeControlService().control(request)
    client_result = M2607Client().control(request)

    assert client_result.model_dump(mode="json") == service_result.model_dump(mode="json")
    assert M2607Client().verify(client_result).result_digest == client_result.result_digest


def test_typer_exports_schema_and_refuses_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    schema_path = tmp_path / "request.schema.json"

    exported = runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)])
    refused = runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)])

    assert exported.exit_code == 0, exported.stdout
    assert json.loads(schema_path.read_text(encoding="utf-8"))["x-glio-contract"]["provisionalAbi"]
    assert refused.exit_code != 0
    assert "overwrite" in refused.output.lower()


def test_typer_control_then_verify_canonical_file(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(_request()))

    controlled = runner.invoke(
        cli_app, ["control", str(request_path), "--output", str(result_path)]
    )
    verified = runner.invoke(cli_app, ["verify", str(result_path)])

    assert controlled.exit_code == 0, controlled.stdout
    assert verified.exit_code == 0, verified.stdout
    assert json.loads(verified.stdout)["verified"] is True

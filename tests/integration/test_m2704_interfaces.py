"""Strict FastAPI, Typer, and SDK parity tests for M27-04."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m27_04 import contract_json_schemas
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.api import create_app
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.cli import app
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.sdk import M2704Client
from tests.runtime.test_m2704_runtime import _request

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_CONTENT = 422


def test_api_schema_validate_publish_verify_and_sanitized_errors() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    with TestClient(create_app()) as client:
        schemas = client.get("/v1/modules/M27-04/schemas")
        schema = client.get("/v1/modules/M27-04/schemas/request")
        validated = client.post("/v1/modules/M27-04/validate", json=payload)
        published = client.post("/v1/modules/M27-04/publish", json=payload)
        verified = client.post("/v1/modules/M27-04/verify", json=published.json())
        malformed = client.post("/v1/modules/M27-04/publish", content=b"{not-json")
        unknown = client.get("/v1/modules/M27-04/schemas/unknown")

    assert schemas.status_code == HTTP_OK
    assert set(schemas.json()) == set(contract_json_schemas())
    assert schema.status_code == HTTP_OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert validated.status_code == HTTP_OK
    assert published.status_code == HTTP_OK
    assert verified.status_code == HTTP_OK
    assert verified.json()["verified"] is True
    assert malformed.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert "Traceback" not in malformed.text
    assert unknown.status_code == HTTP_NOT_FOUND


def test_api_rejects_duplicate_json_keys_and_true_async_claims() -> None:
    request = _request().model_dump(mode="json")
    duplicate = b'{"request_id":"first","request_id":"second"}'
    with TestClient(create_app()) as client:
        duplicate_response = client.post("/v1/modules/M27-04/validate", content=duplicate)
        claim = dict(request)
        claim["unknown_claim"] = True
        claim_response = client.post("/v1/modules/M27-04/validate", json=claim)

    assert duplicate_response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert claim_response.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_cli_schema_validate_publish_verify_and_no_overwrite(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    schema_path = tmp_path / "request-schema.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    exported = runner.invoke(app, ["export-schema", "request", "--output", str(schema_path)])
    validated = runner.invoke(app, ["validate", str(request_path)])
    published = runner.invoke(app, ["publish", str(request_path), "--output", str(result_path)])
    verified = runner.invoke(app, ["verify", str(result_path)])
    overwrite = runner.invoke(app, ["export-schema", "request", "--output", str(schema_path)])

    assert exported.exit_code == 0, exported.output
    assert validated.exit_code == 0, validated.output
    assert published.exit_code == 0, published.output
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.output)["verified"] is True
    assert overwrite.exit_code != 0
    assert "Traceback" not in overwrite.output


def test_sdk_and_plugin_use_the_same_canonical_service_boundary() -> None:
    request = _request()
    client = M2704Client()
    sdk_result = client.publish(request)
    assert client.verify(sdk_result) == sdk_result
    assert client.publish_json(request) == sdk_result.model_dump(mode="json")

"""FastAPI, SDK, Typer, and plugin parity tests for M26-04."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m26_04 import (
    M2604_MAX_CANONICAL_REQUEST_BYTES,
    M2604_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_04_api_sdk_cli_gateway import (
    GatewaySubmission,
    M2604Client,
    M2604Plugin,
    api,
    cli,
)
from tests.contract.test_m2604_contract import _request

if TYPE_CHECKING:
    from pathlib import Path

_SCHEMA_COUNT = 12


def test_api_schema_validate_publish_and_verify_parity() -> None:
    request = _request()
    client = TestClient(api.create_app())
    schemas = client.get("/v1/modules/M26-04/schemas")
    assert schemas.status_code == HTTPStatus.OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    payload = request.model_dump_json()
    validated = client.post(
        "/v1/modules/M26-04/validate",
        content=payload,
        headers={"content-type": "application/json"},
    )
    published = client.post(
        "/v1/modules/M26-04/publish",
        content=payload,
        headers={"content-type": "application/json"},
    )
    assert validated.status_code == HTTPStatus.OK
    assert published.status_code == HTTPStatus.OK
    verified = client.post("/v1/modules/M26-04/verify", json=published.json())
    assert verified.status_code == HTTPStatus.OK
    assert verified.json()["verified"] is True


def test_api_unknown_schema_and_duplicate_json_are_sanitized() -> None:
    client = TestClient(api.create_app())
    unknown = client.get("/v1/modules/M26-04/schemas/unknown")
    assert unknown.status_code == HTTPStatus.NOT_FOUND
    duplicate = client.post(
        "/v1/modules/M26-04/validate",
        content=b'{"request_id":"first","request_id":"secret"}',
        headers={"content-type": "application/json"},
    )
    assert duplicate.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "secret" not in duplicate.text


def test_api_verify_rejects_nonobject_and_malformed_json() -> None:
    client = TestClient(api.create_app())
    nonobject = client.post("/v1/modules/M26-04/verify", json=["bad"])
    malformed = client.post(
        "/v1/modules/M26-04/verify",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert nonobject.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_api_enforces_distinct_request_and_result_stream_limits() -> None:
    client = TestClient(api.create_app())
    oversized_request = b"{" + b" " * M2604_MAX_CANONICAL_REQUEST_BYTES + b"}"
    oversized_result = b"{" + b" " * M2604_MAX_CANONICAL_RESULT_BYTES + b"}"
    request_response = client.post("/v1/modules/M26-04/validate", content=oversized_request)
    result_response = client.post("/v1/modules/M26-04/verify", content=oversized_result)

    assert request_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert result_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    between_limits = b"{" + b" " * M2604_MAX_CANONICAL_REQUEST_BYTES + b"}"
    assert api._parse_object(between_limits, max_bytes=M2604_MAX_CANONICAL_RESULT_BYTES) == {}
    with pytest.raises(HTTPException, match="request JSON is invalid"):
        api._parse_object(between_limits, max_bytes=M2604_MAX_CANONICAL_REQUEST_BYTES)


def test_sdk_and_plugin_return_same_canonical_result() -> None:
    request = _request()
    sdk_result = M2604Client().publish(request)
    plugin = M2604Plugin()
    token = plugin.validate(GatewaySubmission(request))
    plugin_result = plugin.run(token)
    assert sdk_result == plugin_result
    assert M2604Client().verify(sdk_result) == sdk_result


def test_plugin_rejects_unwrapped_and_forged_tokens() -> None:
    plugin = M2604Plugin()
    with pytest.raises(TypeError):
        plugin.validate(request=_request())  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_cli_schema_publish_verify_and_no_overwrite(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    schema_path = tmp_path / "schema.json"
    exported = runner.invoke(cli.app, ["export-schema", "request", "--output", str(schema_path)])
    assert exported.exit_code == 0
    validated = runner.invoke(cli.app, ["validate", str(request_path)])
    published = runner.invoke(cli.app, ["publish", str(request_path), "--output", str(result_path)])
    verified = runner.invoke(cli.app, ["verify", str(result_path)])
    overwrite = runner.invoke(cli.app, ["export-schema", "request", "--output", str(schema_path)])
    assert validated.exit_code == 0
    assert published.exit_code == 0
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True
    assert overwrite.exit_code != 0


def test_cli_unknown_and_bad_input_are_sanitized(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(cli.app, ["export-schema", "unknown"])
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    invalid = runner.invoke(cli.app, ["validate", str(bad)])
    assert unknown.exit_code != 0
    assert "unknown M26-04 contract" in unknown.output
    assert invalid.exit_code != 0

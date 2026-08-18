"""FastAPI, Typer, and canonical interface parity tests for M26-01."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m26_01 import (
    M2601_MAX_CANONICAL_REQUEST_BYTES,
    M2601_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_01_registry_configuration_service import (
    api as m2601_api,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_01_registry_configuration_service import (
    cli as m2601_cli,
)
from tests.contract.test_m2601_deep import _request

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_SCHEMA_COUNT = 8


def test_fastapi_schema_validate_register_verify_parity() -> None:
    request = _request()
    client = TestClient(m2601_api.create_app())
    schemas = client.get("/v1/modules/M26-01/schemas")
    assert schemas.status_code == HTTPStatus.OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    assert client.get("/v1/modules/M26-01/schemas/unknown").status_code == HTTPStatus.NOT_FOUND

    body = request.model_dump_json()
    headers = {"content-type": "application/json"}
    validated = client.post("/v1/modules/M26-01/validate", content=body, headers=headers)
    assert validated.status_code == HTTPStatus.OK
    registered = client.post("/v1/modules/M26-01/register", content=body, headers=headers)
    assert registered.status_code == HTTPStatus.OK
    result = registered.json()
    verified = client.post("/v1/modules/M26-01/verify", json={"result": result})
    assert verified.status_code == HTTPStatus.OK
    assert verified.json()["verified"] is True


def test_fastapi_sanitizes_invalid_and_nonobject_replay() -> None:
    client = TestClient(m2601_api.create_app())
    invalid = client.post(
        "/v1/modules/M26-01/register",
        content=b'{"secret_submission":"do-not-echo"}',
        headers={"content-type": "application/json"},
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "secret_submission" not in invalid.text
    assert "M26-01 contract" in invalid.text

    nonobject = client.post("/v1/modules/M26-01/verify", content=b"[]")
    assert nonobject.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "replay envelope JSON must be an object" in nonobject.text


def test_typer_round_trip_schema_register_verify_and_no_overwrite(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    schema = runner.invoke(m2601_cli.app, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["$schema"].endswith("2020-12/schema")
    validated = runner.invoke(m2601_cli.app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["request_id"] == request.request_id

    registered = runner.invoke(
        m2601_cli.app, ["register", str(request_path), "--output", str(result_path)]
    )
    assert registered.exit_code == 0
    verified = runner.invoke(m2601_cli.app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True

    overwrite = runner.invoke(
        m2601_cli.app, ["register", str(request_path), "--output", str(result_path)]
    )
    assert overwrite.exit_code != 0
    assert "refusing to overwrite" in overwrite.output


def test_typer_sanitizes_unknown_schema_and_malformed_input(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m2601_cli.app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
    assert "unknown M26-01 contract" in unknown.output
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not-json", encoding="utf-8")
    response = runner.invoke(m2601_cli.app, ["validate", str(malformed)])
    assert response.exit_code != 0
    assert "strict M26-01 request contract" in response.output


def test_interfaces_reject_oversized_request_and_result_before_parse(tmp_path: Path) -> None:
    request_path = tmp_path / "oversized-request.json"
    result_path = tmp_path / "oversized-result.json"
    request_path.write_bytes(b"{" + b"a" * M2601_MAX_CANONICAL_REQUEST_BYTES + b"}")
    result_path.write_bytes(b"{" + b"a" * M2601_MAX_CANONICAL_RESULT_BYTES + b"}")

    runner = CliRunner()
    request_response = runner.invoke(m2601_cli.app, ["validate", str(request_path)])
    result_response = runner.invoke(m2601_cli.app, ["verify", str(result_path)])
    assert request_response.exit_code != 0
    assert result_response.exit_code != 0
    assert "strict M26-01 request contract" in request_response.output
    assert "valid M26-01 result" in result_response.output
    assert "Traceback" not in request_response.output + result_response.output

    client = TestClient(m2601_api.create_app())
    oversized = b"{" + b"a" * M2601_MAX_CANONICAL_RESULT_BYTES + b"}"
    api_response = client.post("/v1/modules/M26-01/verify", content=oversized)
    assert api_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "replay envelope JSON is invalid" in api_response.text
    assert "StrictJsonError" not in api_response.text


def test_api_verify_parser_uses_result_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[int] = []

    def capture(body: bytes, *, max_bytes: int) -> dict[str, object]:
        del body
        observed.append(max_bytes)
        return {}

    monkeypatch.setattr(m2601_api, "strict_json_loads", capture)
    response = TestClient(m2601_api.create_app()).post("/v1/modules/M26-01/verify", content=b"{}")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert observed == [M2601_MAX_CANONICAL_RESULT_BYTES]

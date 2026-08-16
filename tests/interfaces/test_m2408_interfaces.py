"""FastAPI, Typer, and canonical parity tests for M24-08."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material.m24_08_evidence_gate_release_adjudicator import (
    api as m2408_api,
)
from glio_proteogen.modules.c21_reference_material.m24_08_evidence_gate_release_adjudicator import (
    cli as m2408_cli,
)
from tests.contract.test_m2408_deep import _request

if TYPE_CHECKING:
    from pathlib import Path

_SCHEMA_COUNT = 10


def test_fastapi_schema_validate_adjudicate_verify_parity() -> None:
    request = _request()
    client = TestClient(m2408_api.create_app())

    schemas = client.get("/v1/modules/M24-08/schemas")
    assert schemas.status_code == HTTPStatus.OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    assert client.get("/v1/modules/M24-08/schemas/unknown").status_code == HTTPStatus.NOT_FOUND

    request_body = request.model_dump_json()
    headers = {"content-type": "application/json"}
    validated = client.post("/v1/modules/M24-08/validate", content=request_body, headers=headers)
    assert validated.status_code == HTTPStatus.OK
    adjudicated = client.post(
        "/v1/modules/M24-08/adjudicate", content=request_body, headers=headers
    )
    assert adjudicated.status_code == HTTPStatus.OK
    result = adjudicated.json()
    verified = client.post("/v1/modules/M24-08/verify", json={"result": result})
    assert verified.status_code == HTTPStatus.OK
    assert verified.json()["verified"] is True
    assert verified.json()["result_digest"] == result["result_digest"]


def test_fastapi_rejects_malformed_json_and_sanitizes_contract_details() -> None:
    client = TestClient(m2408_api.create_app())
    response = client.post(
        "/v1/modules/M24-08/adjudicate",
        content=b'{"secret_submission":"do-not-echo"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "secret_submission" not in response.text
    assert "M24-08 contract" in response.text

    malformed = client.post(
        "/v1/modules/M24-08/verify",
        content=b"[]",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "request JSON must be an object" in malformed.text


def test_typer_round_trip_no_overwrite_and_schema_validation(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    schema = runner.invoke(m2408_cli.app, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["$schema"].endswith("2020-12/schema")

    validated = runner.invoke(m2408_cli.app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["request_id"] == request.request_id

    adjudicated = runner.invoke(
        m2408_cli.app, ["adjudicate", str(request_path), "--output", str(result_path)]
    )
    assert adjudicated.exit_code == 0
    assert result_path.exists()
    verified = runner.invoke(m2408_cli.app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True

    overwrite = runner.invoke(
        m2408_cli.app, ["adjudicate", str(request_path), "--output", str(result_path)]
    )
    assert overwrite.exit_code != 0
    assert "refusing to overwrite" in overwrite.output


def test_typer_sanitizes_unknown_schema_and_invalid_request(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m2408_cli.app, ["export-schema", "secret-internal-schema"])
    assert unknown.exit_code != 0
    assert "unknown M24-08 contract" in unknown.output

    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"secret_submission":"do-not-echo"}', encoding="utf-8")
    response = runner.invoke(m2408_cli.app, ["validate", str(invalid)])
    assert response.exit_code != 0
    assert "secret_submission" not in response.output
    assert "strict M24-08 request contract" in response.output

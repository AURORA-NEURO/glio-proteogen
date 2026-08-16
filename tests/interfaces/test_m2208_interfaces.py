"""FastAPI, Typer, and canonical interface parity tests for M22-08."""

import json
from http import HTTPStatus
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material.m22_08_evidence_gate_release_adjudicator import (
    api as m2208_api,
)
from glio_proteogen.modules.c21_reference_material.m22_08_evidence_gate_release_adjudicator import (
    cli as m2208_cli,
)
from tests.contract.test_m2208_contract import _request

_SCHEMA_COUNT = 10


def test_fastapi_schema_validate_adjudicate_verify_parity() -> None:
    request = _request()
    client = TestClient(m2208_api.create_app())
    schemas = client.get("/v1/modules/M22-08/schemas")
    assert schemas.status_code == HTTPStatus.OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    assert client.get("/v1/modules/M22-08/schemas/unknown").status_code == HTTPStatus.NOT_FOUND

    request_body = request.model_dump_json()
    validated = client.post(
        "/v1/modules/M22-08/validate",
        content=request_body,
        headers={"content-type": "application/json"},
    )
    assert validated.status_code == HTTPStatus.OK
    adjudicated = client.post(
        "/v1/modules/M22-08/adjudicate",
        content=request_body,
        headers={"content-type": "application/json"},
    )
    assert adjudicated.status_code == HTTPStatus.OK
    result = adjudicated.json()
    verified = client.post(
        "/v1/modules/M22-08/verify",
        json=result,
    )
    assert verified.status_code == HTTPStatus.OK
    assert verified.json()["verified"] is True


def test_fastapi_sanitizes_invalid_request() -> None:
    client = TestClient(m2208_api.create_app())
    response = client.post(
        "/v1/modules/M22-08/adjudicate",
        content=b'{"secret_submission":"do-not-echo"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "secret_submission" not in response.text
    assert "M22-08 contract" in response.text


def test_typer_export_validate_adjudicate_verify_and_no_overwrite(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    schema = runner.invoke(m2208_cli.app, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["$schema"].endswith("2020-12/schema")

    validated = runner.invoke(m2208_cli.app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["request_id"] == request.request_id

    adjudicated = runner.invoke(
        m2208_cli.app,
        ["adjudicate", str(request_path), "--output", str(result_path)],
    )
    assert adjudicated.exit_code == 0
    assert result_path.exists()
    verified = runner.invoke(m2208_cli.app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True

    overwrite = runner.invoke(
        m2208_cli.app,
        ["adjudicate", str(request_path), "--output", str(result_path)],
    )
    assert overwrite.exit_code != 0
    assert "refusing to overwrite" in overwrite.output

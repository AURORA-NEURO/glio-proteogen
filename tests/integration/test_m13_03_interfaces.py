"""FastAPI and Typer parity tests for M13-03."""

from __future__ import annotations

import json
from http import HTTPStatus

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1303 import app, m1303_app
from glio_proteogen.contracts.m13_03 import MechanisticConstructionStatus
from tests.contract.test_m13_03_runtime import request


def test_api_constructs_supported_request_and_exports_schema() -> None:
    payload = json.loads(request().model_dump_json())
    with TestClient(app) as client:
        response = client.post("/v1/modules/M13-03/features", json=payload)
        schema = client.get("/v1/m13-03/schema/output")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == MechanisticConstructionStatus.CONSTRUCTED.value
    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True


def test_api_rejects_duplicate_keys_without_echoing_payload() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/modules/M13-03/features",
            content=b'{"request_id":"safe","request_id":"secret"}',
        )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "secret" not in response.text
    assert response.json()["error"]["type"] == "json_duplicate_key"


def test_api_verifies_released_result() -> None:
    payload = json.loads(request().model_dump_json())
    with TestClient(app) as client:
        result = client.post("/v1/modules/M13-03/features", json=payload).json()
        verified = client.post("/v1/modules/M13-03/verify", json=result)

    assert verified.status_code == HTTPStatus.OK
    assert verified.json()["verified"] is True


def test_cli_schema_is_no_overwrite_and_unknown_is_safe(tmp_path) -> None:
    output = tmp_path / "schema.json"
    runner = CliRunner()
    first = runner.invoke(m1303_app, ["export-schema", "request", "--output", str(output)])
    second = runner.invoke(m1303_app, ["export-schema", "request", "--output", str(output)])
    unknown = runner.invoke(m1303_app, ["export-schema", "secret", "--output", str(tmp_path / "x")])

    assert first.exit_code == 0
    assert second.exit_code != 0
    assert unknown.exit_code != 0
    assert "secret" not in unknown.stdout


def test_cli_construct_and_verify_round_trip(tmp_path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    constructed = runner.invoke(
        m1303_app,
        ["construct", str(request_path), "--output", str(result_path)],
    )
    verified = runner.invoke(m1303_app, ["verify", str(result_path)])

    assert constructed.exit_code == 0, constructed.stdout
    assert verified.exit_code == 0, verified.stdout
    assert json.loads(verified.stdout)["verified"] is True

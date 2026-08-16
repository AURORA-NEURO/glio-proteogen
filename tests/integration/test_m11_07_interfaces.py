"""HTTP and CLI parity tests for M11-07."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1107 import app, m1107_app
from tests.modules.c11_protein_native_subtype.test_m11_07_engine import _request

_OK = 200
_BAD_REQUEST = 400
_FORBIDDEN = 403


def test_api_schema_and_adjudication() -> None:
    request = _request()
    with TestClient(app) as client:
        schema = client.get("/v1/modules/M11-07/schema/request")
        response = client.post(
            "/v1/modules/M11-07/plausibility",
            content=request.model_dump_json(),
            headers={"content-type": "application/json"},
        )
    assert schema.status_code == _OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert response.status_code == _OK
    assert response.json()["status"] == "adjudicated"


def test_api_sanitizes_duplicate_and_unauthorized_inputs() -> None:
    request_json = _request().model_dump_json()
    with TestClient(app) as client:
        duplicate = client.post(
            "/v1/modules/M11-07/plausibility",
            content=request_json[:-1] + ',"request_id":"hostile"}',
        )
        unauthorized = _request().model_dump(mode="json")
        unauthorized["context"]["references"]["support"]["state"] = "rejected"
        denied = client.post(
            "/v1/modules/M11-07/plausibility",
            content=json.dumps(unauthorized),
        )
    assert duplicate.status_code == _BAD_REQUEST
    assert denied.status_code == _FORBIDDEN
    assert "hostile" not in duplicate.text


def test_api_verify_and_cli_adjudicate_verify(tmp_path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    adjudicate = runner.invoke(
        m1107_app,
        ["adjudicate", str(request_path), "--output", str(result_path)],
    )
    assert adjudicate.exit_code == 0, adjudicate.output
    verify = runner.invoke(m1107_app, ["verify", str(request_path), str(result_path)])
    assert verify.exit_code == 0, verify.output
    result_document = json.loads(result_path.read_text(encoding="utf-8"))
    envelope = {
        "request": request.model_dump(mode="json"),
        "result": result_document,
    }
    with TestClient(app) as client:
        response = client.post("/v1/modules/M11-07/verify", json=envelope)
    assert response.status_code == _OK
    assert response.json()["verified"] is True


def test_cli_schema_no_overwrite(tmp_path) -> None:
    output = tmp_path / "schema.json"
    runner = CliRunner()
    first = runner.invoke(m1107_app, ["export-schema", "output", "--output", str(output)])
    second = runner.invoke(m1107_app, ["export-schema", "output", "--output", str(output)])
    assert first.exit_code == 0, first.output
    assert second.exit_code != 0

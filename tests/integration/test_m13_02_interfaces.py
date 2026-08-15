"""API/CLI parity and sanitized-error tests for M13-02."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1302 import app, m1302_app
from tests.contract.test_m13_02_runtime import _request

_HTTP_OK = 200
_HTTP_BAD_REQUEST = 400
_HTTP_FORBIDDEN = 403


def test_api_schema_and_stratification_parity() -> None:
    request = _request()
    client = TestClient(app)
    schema = client.get("/v1/m13-02/schema/request")
    assert schema.status_code == _HTTP_OK
    assert schema.json()["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M13-02"
    response = client.post("/v1/modules/M13-02/context", json=request.model_dump(mode="json"))
    assert response.status_code == _HTTP_OK
    body = response.json()
    assert body["status"] == "stratified"
    assert body["parent_target"] == "proteotype"
    verified = client.post("/v1/modules/M13-02/verify", json=body)
    assert verified.status_code == _HTTP_OK
    assert verified.json() == {"verified": True}


def test_api_authentication_and_duplicate_key_errors_are_sanitized() -> None:
    request = _request().model_copy(update={"context": _request().context.model_copy(deep=True)})
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "support": request.context.references.support.model_copy(
                        update={"state": "rejected"}
                    )
                }
            )
        }
    )
    denied = request.model_copy(update={"context": denied_context})
    client = TestClient(app)
    response = client.post("/v1/modules/M13-02/context", json=denied.model_dump(mode="json"))
    assert response.status_code == _HTTP_FORBIDDEN
    assert "support" not in response.text
    duplicate = json.dumps(request.model_dump(mode="json"))[:-1] + ',"request_id":"x"}'
    duplicate_response = client.post(
        "/v1/modules/M13-02/context",
        content=duplicate,
        headers={"content-type": "application/json"},
    )
    assert duplicate_response.status_code == _HTTP_BAD_REQUEST
    assert duplicate_response.json()["error"]["code"] == "json_duplicate_key"


def test_cli_stratify_export_and_no_overwrite(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(request.model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        m1302_app,
        ["stratify", str(request_path), "--output", str(output_path)],
    )
    assert result.exit_code == 0, result.stdout
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "stratified"
    refused = runner.invoke(
        m1302_app,
        ["stratify", str(request_path), "--output", str(output_path)],
    )
    assert refused.exit_code != 0
    schema = runner.invoke(m1302_app, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert "GLIO-PROTEOGEN-M13-02" in schema.stdout

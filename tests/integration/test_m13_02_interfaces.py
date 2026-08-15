"""API/CLI parity and sanitized-error tests for M13-02."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import m1302
from glio_proteogen.adapters.m1302 import app, m1302_app
from tests.contract.test_m13_02_runtime import _request

_HTTP_OK = 200
_HTTP_BAD_REQUEST = 400
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_CLI_VALIDATION = 2
_CLI_AUTHORIZATION = 3

if TYPE_CHECKING:
    from pathlib import Path


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


def test_api_rejects_unknown_schema_nonobject_invalid_contract_and_tamper() -> None:
    client = TestClient(app)
    unknown = client.get("/v1/m13-02/schema/nope")
    assert unknown.status_code == _HTTP_NOT_FOUND
    nonobject = client.post("/v1/modules/M13-02/context", json=[])
    assert nonobject.status_code == _HTTP_UNPROCESSABLE
    invalid = client.post("/v1/modules/M13-02/context", json={})
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    tampered = client.post("/v1/modules/M13-02/verify", json={"status": "stratified"})
    assert tampered.status_code == _HTTP_UNPROCESSABLE


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


def test_cli_rejects_invalid_schema_json_and_tamper(tmp_path) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    bad_schema = runner.invoke(m1302_app, ["export-schema", "nope"])
    assert bad_schema.exit_code != 0
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("[]", encoding="utf-8")
    invalid = runner.invoke(m1302_app, ["stratify", str(invalid_path)])
    assert invalid.exit_code != 0
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{", encoding="utf-8")
    malformed = runner.invoke(m1302_app, ["stratify", str(malformed_path)])
    assert malformed.exit_code == _CLI_VALIDATION
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text('{"status":"stratified"}', encoding="utf-8")
    tampered = runner.invoke(m1302_app, ["verify", str(tampered_path)])
    assert tampered.exit_code == 1


def test_cli_stdin_valid_auth_validation_and_verify_paths(tmp_path: Path) -> None:
    request = _request()
    runner = CliRunner()
    encoded = json.dumps(request.model_dump(mode="json"))
    stdin = runner.invoke(m1302_app, ["stratify", "-"], input=encoded)
    assert stdin.exit_code == 0
    invalid_path = tmp_path / "invalid-contract.json"
    invalid_path.write_text("{}", encoding="utf-8")
    invalid = runner.invoke(m1302_app, ["stratify", str(invalid_path)])
    assert invalid.exit_code == _CLI_VALIDATION
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
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
        }
    )
    denied_path = tmp_path / "denied.json"
    denied_path.write_text(json.dumps(denied.model_dump(mode="json")), encoding="utf-8")
    denied_result = runner.invoke(m1302_app, ["stratify", str(denied_path)])
    assert denied_result.exit_code == _CLI_AUTHORIZATION
    result = m1302._plugin.run(m1302._plugin.validate(request))
    result_path = tmp_path / "verified-result.json"
    result_path.write_text(json.dumps(result.model_dump(mode="json")), encoding="utf-8")
    verified = runner.invoke(m1302_app, ["verify", str(result_path)])
    assert verified.exit_code == 0


def test_api_maps_runtime_value_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class FailingPlugin:
        def validate(self, _request: object) -> object:
            raise ValueError("safe failure")  # noqa: TRY003 - test seam.

        def run(self, _token: object) -> object:
            raise AssertionError("not reached")  # noqa: TRY003 - test seam.

    monkeypatch.setattr(m1302, "_plugin", FailingPlugin())
    response = TestClient(app).post("/v1/modules/M13-02/context", json={"request_id": "x"})
    assert response.status_code == _HTTP_UNPROCESSABLE

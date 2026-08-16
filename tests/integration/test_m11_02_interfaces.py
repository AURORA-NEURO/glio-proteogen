"""FastAPI, CLI, schema, and strict ingress parity for provisional M11-02."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1102 import create_m1102_app, m1102_app
from glio_proteogen.contracts.m11_02 import contract_json_schema
from glio_proteogen.kernel.models import ConsentState
from tests.modules.c11_protein_native_subtype.test_m11_02_runtime import _request

_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422
_HTTP_FORBIDDEN = 403
_CLI_CONTRACT_ERROR = 2


def test_api_schema_and_stratify_match_contract_and_cli() -> None:
    request = _request()
    document = request.model_dump(mode="json")
    with TestClient(create_m1102_app()) as client:
        schema = client.post("/v1/m11-02/schema/request")
        result = client.post("/v1/m11-02/stratify", content=json.dumps(document))
        validated = client.post("/v1/m11-02/validate", content=json.dumps(document))

    assert schema.status_code == _HTTP_OK
    assert schema.json() == contract_json_schema("request")
    assert result.status_code == _HTTP_OK
    assert validated.status_code == _HTTP_OK
    assert validated.json()["valid"] is True
    cli = CliRunner().invoke(m1102_app, ["stratify", json.dumps(document)])
    assert cli.exit_code == 0, cli.stdout + cli.stderr
    assert json.loads(cli.stdout) == result.json()


def test_api_verifies_result_and_duplicate_json_is_rejected() -> None:
    request = _request().model_dump(mode="json")
    with TestClient(create_m1102_app()) as client:
        result_response = client.post("/v1/m11-02/stratify", content=json.dumps(request))
        verified = client.post("/v1/m11-02/verify", content=result_response.content)
        duplicate = client.post(
            "/v1/m11-02/stratify",
            content=(json.dumps(request)[:-1] + ',"request_id":"duplicate"}'),
        )

    assert result_response.status_code == _HTTP_OK
    assert verified.status_code == _HTTP_OK
    assert verified.json() == result_response.json()
    assert duplicate.status_code == _HTTP_UNPROCESSABLE
    assert duplicate.json()["detail"][0]["type"] == "json_duplicate_key"
    assert "request_id" not in duplicate.text


def test_cli_exports_schema_and_sanitizes_invalid_payload() -> None:
    schema = CliRunner().invoke(m1102_app, ["export-schema", "output"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout) == contract_json_schema("output")
    invalid = CliRunner().invoke(m1102_app, ["validate", '{"request_id": 1}'])
    assert invalid.exit_code == _CLI_CONTRACT_ERROR
    assert "request_id" not in invalid.stderr


def test_api_and_cli_error_paths_are_sanitized_and_bounded(tmp_path) -> None:
    request = _request().model_dump(mode="json")
    denied = (
        _request()
        .model_copy(
            update={
                "context": _request(consent=ConsentState.WITHHELD).context,
            }
        )
        .model_dump(mode="json")
    )
    with TestClient(create_m1102_app()) as client:
        malformed = client.post("/v1/m11-02/validate", content=b"{")
        invalid = client.post(
            "/v1/m11-02/validate",
            content=json.dumps({**request, "request_id": 1}),
        )
        denied_response = client.post("/v1/m11-02/stratify", content=json.dumps(denied))
        denied_validate = client.post("/v1/m11-02/validate", content=json.dumps(denied))
        invalid_stratify = client.post(
            "/v1/m11-02/stratify",
            content=json.dumps({**request, "request_id": 1}),
        )
        verify_invalid = client.post("/v1/m11-02/verify", content=b"{}")
        verify_malformed = client.post("/v1/m11-02/verify", content=b"{")
        verify_tampered = client.post(
            "/v1/m11-02/verify",
            content=json.dumps({"result_digest": "sha256:" + ("b" * 64)}),
        )

    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert malformed.json()["detail"][0]["type"] == "json_invalid_syntax"
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert invalid.json()["detail"]
    assert denied_response.status_code == _HTTP_FORBIDDEN
    assert denied_response.json()["detail"][0]["type"] == "authorization_denied"
    assert denied_validate.status_code == _HTTP_FORBIDDEN
    assert invalid_stratify.status_code == _HTTP_UNPROCESSABLE
    assert verify_invalid.status_code == _HTTP_UNPROCESSABLE
    assert verify_invalid.json()["detail"]
    assert verify_malformed.status_code == _HTTP_UNPROCESSABLE
    assert verify_malformed.json()["detail"][0]["type"] == "json_invalid_syntax"
    assert verify_tampered.status_code == _HTTP_UNPROCESSABLE
    assert verify_tampered.json()["detail"]

    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(m1102_app, ["validate", str(path)]).exit_code == 0
    assert (
        runner.invoke(
            m1102_app,
            ["validate", json.dumps({**request, "request_id": 1})],
        ).exit_code
        == _CLI_CONTRACT_ERROR
    )
    assert runner.invoke(m1102_app, ["validate", "{"]).exit_code == _CLI_CONTRACT_ERROR
    assert runner.invoke(m1102_app, ["stratify", "{"]).exit_code == 1
    assert runner.invoke(m1102_app, ["verify", "{}"]).exit_code == 1
    result = runner.invoke(m1102_app, ["stratify", json.dumps(request)])
    assert result.exit_code == 0
    assert runner.invoke(m1102_app, ["verify", result.stdout]).exit_code == 0
    assert runner.invoke(m1102_app, ["verify", "{"]).exit_code == 1

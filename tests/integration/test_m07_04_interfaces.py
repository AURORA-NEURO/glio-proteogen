"""FastAPI/Typer parity tests for the provisional M07-04 adapter."""

from __future__ import annotations

import json
from http import HTTPStatus

from evals.m07_04.run import request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m0704 import create_m0704_app, m0704_app
from glio_proteogen.contracts.m07_04 import contract_json_schemas
from glio_proteogen.contracts.m07_04.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes

_CLI_CONTRACT_ERROR = 2
_CLI_AUTH_ERROR = 3


def test_api_schema_estimate_verify_and_unknown_schema() -> None:
    client = TestClient(create_m0704_app())
    schema = client.get("/v1/m07-04/schema/output")
    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    result_response = client.post(
        "/v1/m07-04/probabilistic/estimate",
        json=request().model_dump(mode="json"),
    )
    assert result_response.status_code == HTTPStatus.OK
    result = result_response.json()
    assert result["status"] == "estimated"
    verified = client.post("/v1/m07-04/probabilistic/verify", json=result)
    assert verified.status_code == HTTPStatus.OK
    assert verified.json() == result
    assert client.get("/v1/m07-04/schema/missing").status_code == HTTPStatus.NOT_FOUND


def test_api_sanitizes_strict_and_validation_errors() -> None:
    client = TestClient(create_m0704_app())
    duplicate = client.post(
        "/v1/m07-04/probabilistic/estimate",
        content=b'{"request_id":"secret-a","request_id":"secret-b"}',
        headers={"content-type": "application/json"},
    )
    assert duplicate.status_code == HTTPStatus.BAD_REQUEST
    assert "secret" not in duplicate.text
    malformed = client.post(
        "/v1/m07-04/probabilistic/estimate",
        content=b"{",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == HTTPStatus.BAD_REQUEST
    invalid = client.post(
        "/v1/m07-04/probabilistic/estimate",
        json={"request_id": "secret-request", "operation": "wrong"},
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "secret-request" not in invalid.text


def test_api_maps_tamper_failure() -> None:
    client = TestClient(create_m0704_app())
    result = client.post(
        "/v1/m07-04/probabilistic/estimate",
        json=request().model_dump(mode="json"),
    ).json()
    result["estimates"][0]["estimate_value"] = 999.0
    result["result_digest"] = result_payload_digest(result)
    tampered = client.post("/v1/m07-04/probabilistic/verify", json=result)
    assert tampered.status_code == HTTPStatus.CONFLICT
    invalid = client.post("/v1/m07-04/probabilistic/verify", json={"result_id": "bad"})
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_cli_schema_validation_estimate_and_verify_are_canonical(tmp_path) -> None:
    runner = CliRunner()
    all_schema = runner.invoke(m0704_app, ["export-schema", "all"])
    assert all_schema.exit_code == 0
    assert set(json.loads(all_schema.stdout)) == set(contract_json_schemas())
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request().model_dump(mode="json")))
    validated = runner.invoke(m0704_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout) == request().model_dump(mode="json")
    estimated = runner.invoke(m0704_app, ["estimate", str(request_path)])
    assert estimated.exit_code == 0
    result = json.loads(estimated.stdout)
    assert result["status"] == "estimated"
    result_path = tmp_path / "result.json"
    result_path.write_bytes(canonical_json_bytes(result))
    verified = runner.invoke(m0704_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout) == result


def test_cli_unknown_schema_duplicate_and_auth_fail_closed(tmp_path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m0704_app, ["export-schema", "unknown"])
    assert unknown.exit_code == _CLI_CONTRACT_ERROR
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text('{"request_id":"a","request_id":"b"}', encoding="utf-8")
    duplicate = runner.invoke(m0704_app, ["validate", str(duplicate_path)])
    assert duplicate.exit_code == _CLI_CONTRACT_ERROR
    assert "request_id" not in duplicate.output
    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(canonical_json_bytes(request(accepted_controls=False).model_dump(mode="json")))
    denied = runner.invoke(m0704_app, ["estimate", str(denied_path)])
    assert denied.exit_code == _CLI_AUTH_ERROR
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text('{"operation":"wrong"}', encoding="utf-8")
    invalid = runner.invoke(m0704_app, ["estimate", str(invalid_path)])
    assert invalid.exit_code == _CLI_CONTRACT_ERROR

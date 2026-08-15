"""FastAPI/Typer parity tests for the provisional M07-03 adapter."""

from __future__ import annotations

import json
from http import HTTPStatus

from evals.m07_03.run import request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m0703 import create_m0703_app, m0703_app
from glio_proteogen.contracts.m07_03 import contract_json_schemas
from glio_proteogen.contracts.m07_03.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c07_copy_number_dosage.m07_03_mature_baseline_estimator import (
    M0703AuthorizationError,
)

_CLI_CONTRACT_ERROR = 2
_CLI_AUTH_ERROR = 3


def test_api_schema_estimate_verify_and_unknown_schema() -> None:
    client = TestClient(create_m0703_app())
    schema = client.get("/v1/m07-03/schema/output")
    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    result_response = client.post(
        "/v1/m07-03/baseline/estimate",
        json=request().model_dump(mode="json"),
    )
    assert result_response.status_code == HTTPStatus.OK
    result = result_response.json()
    assert result["status"] == "abstained"
    verified = client.post("/v1/m07-03/baseline/verify", json=result)
    assert verified.status_code == HTTPStatus.OK
    assert verified.json() == result
    assert client.get("/v1/m07-03/schema/missing").status_code == HTTPStatus.NOT_FOUND


def test_api_sanitizes_strict_and_validation_errors() -> None:
    client = TestClient(create_m0703_app())
    duplicate = client.post(
        "/v1/m07-03/baseline/estimate",
        content=b'{"request_id":"secret-a","request_id":"secret-b"}',
        headers={"content-type": "application/json"},
    )
    assert duplicate.status_code == HTTPStatus.BAD_REQUEST
    assert "secret" not in duplicate.text
    malformed = client.post(
        "/v1/m07-03/baseline/estimate",
        content=b"{",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == HTTPStatus.BAD_REQUEST
    invalid = client.post(
        "/v1/m07-03/baseline/estimate",
        json={"request_id": "secret-request", "operation": "wrong"},
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "secret-request" not in invalid.text


def test_api_maps_authorization_and_tamper_failures() -> None:
    class AuthorizationFailureService:
        def execute(self, _request: object) -> object:
            raise M0703AuthorizationError

        def verify(self, _result: object) -> object:
            raise AssertionError("verify should not be called")  # noqa: TRY003

    auth_client = TestClient(create_m0703_app(AuthorizationFailureService))
    denied = auth_client.post(
        "/v1/m07-03/baseline/estimate",
        json=request().model_dump(mode="json"),
    )
    assert denied.status_code == HTTPStatus.FORBIDDEN

    client = TestClient(create_m0703_app())
    result = client.post(
        "/v1/m07-03/baseline/estimate",
        json=request().model_dump(mode="json"),
    ).json()
    result["abstention_reason"] = "tampered"
    result["result_digest"] = result_payload_digest(result)
    tampered = client.post("/v1/m07-03/baseline/verify", json=result)
    assert tampered.status_code == HTTPStatus.CONFLICT
    invalid = client.post("/v1/m07-03/baseline/verify", json={"result_id": "bad"})
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_cli_schema_validation_and_estimate_are_canonical(tmp_path) -> None:
    runner = CliRunner()
    all_schema = runner.invoke(m0703_app, ["export-schema", "all"])
    assert all_schema.exit_code == 0
    assert set(json.loads(all_schema.stdout)) == set(contract_json_schemas())
    single_schema = runner.invoke(m0703_app, ["export-schema", "request"])
    assert single_schema.exit_code == 0
    assert json.loads(single_schema.stdout)["x-glio-contract"]["provisionalAbi"] is True
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request().model_dump(mode="json")))
    validated = runner.invoke(m0703_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout) == request().model_dump(mode="json")
    estimated = runner.invoke(m0703_app, ["estimate", str(request_path)])
    assert estimated.exit_code == 0
    assert json.loads(estimated.stdout)["status"] == "abstained"


def test_cli_unknown_schema_duplicate_and_auth_fail_closed(tmp_path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m0703_app, ["export-schema", "unknown"])
    assert unknown.exit_code == _CLI_CONTRACT_ERROR
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text('{"request_id":"a","request_id":"b"}', encoding="utf-8")
    duplicate = runner.invoke(m0703_app, ["validate", str(duplicate_path)])
    assert duplicate.exit_code == _CLI_CONTRACT_ERROR
    assert "request_id" not in duplicate.output
    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(
        canonical_json_bytes(
            request(accepted_controls=False).model_dump(mode="json")
        )
    )
    denied = runner.invoke(m0703_app, ["estimate", str(denied_path)])
    assert denied.exit_code == _CLI_AUTH_ERROR
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text('{"operation":"wrong"}', encoding="utf-8")
    invalid = runner.invoke(m0703_app, ["estimate", str(invalid_path)])
    assert invalid.exit_code == _CLI_CONTRACT_ERROR

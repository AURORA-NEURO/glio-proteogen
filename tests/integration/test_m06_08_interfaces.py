"""API/CLI parity tests for the provisional M06-08 adapter."""

from __future__ import annotations

import json
from http import HTTPStatus

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m0608 import create_m0608_app, m0608_app
from glio_proteogen.contracts.m06_08 import contract_json_schemas
from glio_proteogen.kernel.canonical import canonical_json_bytes
from tests.modules.c06_protein_abundance.test_m06_08_runtime import request

_CLI_CONTRACT_ERROR = 2


def test_api_schema_publish_and_verify_have_sanitized_parity() -> None:
    client = TestClient(create_m0608_app())
    schema_response = client.get("/v1/m06-08/schema/output")
    assert schema_response.status_code == HTTPStatus.OK
    assert schema_response.json()["x-glio-contract"]["provisionalAbi"] is True
    payload = request().model_dump(mode="json")
    published = client.post("/v1/m06-08/evidence/publish", json=payload)
    assert published.status_code == HTTPStatus.OK
    result = published.json()
    assert result["status"] == "abstained"
    verified = client.post("/v1/m06-08/evidence/verify", json=result)
    assert verified.status_code == HTTPStatus.OK
    assert verified.json() == result


def test_api_rejects_unknown_schema_and_invalid_json_without_echoing_values() -> None:
    client = TestClient(create_m0608_app())
    unknown = client.get("/v1/m06-08/schema/not-a-contract")
    assert unknown.status_code == HTTPStatus.NOT_FOUND
    invalid = client.post(
        "/v1/m06-08/evidence/publish",
        json={"request_id": "secret-request", "operation": "wrong"},
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "secret-request" not in invalid.text


def test_cli_schema_and_validation_are_deterministic(tmp_path) -> None:
    runner = CliRunner()
    schema = runner.invoke(m0608_app, ["export-schema", "all"])
    assert schema.exit_code == 0
    assert set(json.loads(schema.stdout)) == set(contract_json_schemas())
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request().model_dump(mode="json")))
    validated = runner.invoke(m0608_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout) == request().model_dump(mode="json")
    published = runner.invoke(m0608_app, ["publish", str(request_path)])
    assert published.exit_code == 0
    assert json.loads(published.stdout)["status"] == "abstained"


def test_cli_unknown_schema_and_duplicate_json_fail_closed(tmp_path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m0608_app, ["export-schema", "unknown"])
    assert unknown.exit_code == _CLI_CONTRACT_ERROR
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text('{"request_id":"a","request_id":"b"}', encoding="utf-8")
    duplicate = runner.invoke(m0608_app, ["validate", str(duplicate_path)])
    assert duplicate.exit_code == _CLI_CONTRACT_ERROR
    assert "request_id" not in duplicate.output

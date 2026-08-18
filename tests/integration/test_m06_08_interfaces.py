"""API/CLI parity tests for the provisional M06-08 adapter."""

from __future__ import annotations

import json
from http import HTTPStatus

from evals.m06_08.run import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m0608 import create_m0608_app, m0608_app
from glio_proteogen.contracts.m06_08 import contract_json_schemas
from glio_proteogen.contracts.m06_08.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c06_protein_abundance.m06_08_evidence_explanation_publisher import (
    M0608EvidencePublisherAuthorizationError,
)
from tests.modules.c06_protein_abundance.test_m06_08_runtime import request

_CLI_CONTRACT_ERROR = 2
_CLI_AUTH_ERROR = 3
_CLI_REPLAY_ERROR = 3


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
    malformed = client.post(
        "/v1/m06-08/evidence/publish",
        content=b"{",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == HTTPStatus.BAD_REQUEST


def test_api_maps_strict_and_authorization_failures() -> None:
    client = TestClient(create_m0608_app())
    duplicate = client.post(
        "/v1/m06-08/evidence/publish",
        content=b'{"operation":"x","operation":"y"}',
        headers={"content-type": "application/json"},
    )
    assert duplicate.status_code == HTTPStatus.BAD_REQUEST
    invalid = request().model_dump(mode="json")
    invalid["source_artifacts"] = []
    validation = client.post("/v1/m06-08/evidence/publish", json=invalid)
    assert validation.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    class AuthorizationFailureService:
        def execute(self, _request: object) -> object:
            raise M0608EvidencePublisherAuthorizationError

        def verify(self, _result: object) -> object:
            raise AssertionError("verify should not be called")  # noqa: TRY003

    auth_client = TestClient(create_m0608_app(AuthorizationFailureService))
    denied = auth_client.post(
        "/v1/m06-08/evidence/publish",
        json=build_request().model_dump(mode="json"),
    )
    assert denied.status_code == HTTPStatus.FORBIDDEN


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
    published_payload = json.loads(published.stdout)
    assert published_payload["status"] == "abstained"
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(published_payload), encoding="utf-8")
    verified = runner.invoke(m0608_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout) == published_payload
    forged = dict(published_payload)
    forged["abstention_reason"] = "forged replay explanation"
    forged["result_digest"] = result_payload_digest(forged)
    result_path.write_text(json.dumps(forged), encoding="utf-8")
    rejected = runner.invoke(m0608_app, ["verify", str(result_path)])
    assert rejected.exit_code == _CLI_REPLAY_ERROR
    assert "replay verification failed" in rejected.output


def test_cli_unknown_schema_and_duplicate_json_fail_closed(tmp_path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m0608_app, ["export-schema", "unknown"])
    assert unknown.exit_code == _CLI_CONTRACT_ERROR
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text('{"request_id":"a","request_id":"b"}', encoding="utf-8")
    duplicate = runner.invoke(m0608_app, ["validate", str(duplicate_path)])
    assert duplicate.exit_code == _CLI_CONTRACT_ERROR
    assert "request_id" not in duplicate.output


def test_api_verify_maps_tamper_and_invalid_envelope() -> None:
    client = TestClient(create_m0608_app())
    result = client.post(
        "/v1/m06-08/evidence/publish",
        json=request().model_dump(mode="json"),
    ).json()
    result["abstention_reason"] = "replay differs"
    result["result_digest"] = result_payload_digest(result)
    tamper = client.post("/v1/m06-08/evidence/verify", json=result)
    assert tamper.status_code == HTTPStatus.CONFLICT
    invalid = client.post("/v1/m06-08/evidence/verify", json={"result_id": "bad"})
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_cli_valid_schema_and_publish_failures(tmp_path) -> None:
    runner = CliRunner()
    exported = runner.invoke(m0608_app, ["export-schema", "request"])
    assert exported.exit_code == 0
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text('{"operation":"wrong"}', encoding="utf-8")
    invalid = runner.invoke(m0608_app, ["publish", str(invalid_path)])
    assert invalid.exit_code == _CLI_CONTRACT_ERROR
    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(
        canonical_json_bytes(build_request(accepted_controls=False).model_dump(mode="json"))
    )
    denied = runner.invoke(m0608_app, ["publish", str(denied_path)])
    assert denied.exit_code == _CLI_AUTH_ERROR

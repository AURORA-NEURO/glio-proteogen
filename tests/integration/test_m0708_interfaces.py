"""FastAPI/Typer strict-parity tests for provisional M07-08."""

from __future__ import annotations

import json
from http import HTTPStatus

from evals.m07_08.run import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m0708 import create_m0708_app, m0708_app
from glio_proteogen.contracts.m07_08 import contract_json_schemas
from glio_proteogen.contracts.m07_08.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c07_copy_number_dosage.m07_08_evidence_explanation_publisher import (
    M0708EvidencePublisherAuthorizationError,
)

_CLI_CONTRACT_ERROR = 2
_CLI_AUTH_ERROR = 3


def test_api_schema_publish_and_verify_have_canonical_parity() -> None:
    client = TestClient(create_m0708_app())
    schema_response = client.get("/v1/m07-08/schema/output")
    assert schema_response.status_code == HTTPStatus.OK
    assert schema_response.json()["x-glio-contract"]["provisionalAbi"] is True
    payload = build_request().model_dump(mode="json")
    published = client.post("/v1/m07-08/evidence/publish", json=payload)
    assert published.status_code == HTTPStatus.OK
    result = published.json()
    assert result["status"] == "abstained"
    verified = client.post("/v1/m07-08/evidence/verify", json=result)
    assert verified.status_code == HTTPStatus.OK
    assert verified.json() == result


def test_api_rejects_unknown_schema_invalid_json_and_duplicate_keys() -> None:
    client = TestClient(create_m0708_app())
    assert client.get("/v1/m07-08/schema/not-a-contract").status_code == HTTPStatus.NOT_FOUND
    invalid = client.post(
        "/v1/m07-08/evidence/publish",
        json={"request_id": "secret-request", "operation": "wrong"},
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "secret-request" not in invalid.text
    malformed = client.post(
        "/v1/m07-08/evidence/publish",
        content=b"{",
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == HTTPStatus.BAD_REQUEST
    duplicate = client.post(
        "/v1/m07-08/evidence/publish",
        content=b'{"operation":"x","operation":"y"}',
        headers={"content-type": "application/json"},
    )
    assert duplicate.status_code == HTTPStatus.BAD_REQUEST


def test_api_maps_authorization_and_validation_failures() -> None:
    client = TestClient(create_m0708_app())
    invalid = build_request().model_dump(mode="json")
    invalid["source_artifacts"] = []
    response = client.post("/v1/m07-08/evidence/publish", json=invalid)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    class AuthorizationFailureService:
        def execute(self, _request: object) -> object:
            raise M0708EvidencePublisherAuthorizationError

        def verify(self, _result: object) -> object:
            raise AssertionError("verify should not be called")  # noqa: TRY003

    denied_client = TestClient(create_m0708_app(AuthorizationFailureService))
    denied = denied_client.post(
        "/v1/m07-08/evidence/publish",
        json=build_request().model_dump(mode="json"),
    )
    assert denied.status_code == HTTPStatus.FORBIDDEN


def test_cli_schema_validation_and_publish_are_deterministic(tmp_path) -> None:
    runner = CliRunner()
    schema = runner.invoke(m0708_app, ["export-schema", "all"])
    assert schema.exit_code == 0
    assert set(json.loads(schema.stdout)) == set(contract_json_schemas())
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(build_request().model_dump(mode="json")))
    validated = runner.invoke(m0708_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout) == build_request().model_dump(mode="json")
    published = runner.invoke(m0708_app, ["publish", str(request_path)])
    assert published.exit_code == 0
    assert json.loads(published.stdout)["status"] == "abstained"


def test_cli_unknown_schema_duplicate_and_authorization_fail_closed(tmp_path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m0708_app, ["export-schema", "unknown"])
    assert unknown.exit_code == _CLI_CONTRACT_ERROR
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text('{"request_id":"a","request_id":"b"}', encoding="utf-8")
    duplicate = runner.invoke(m0708_app, ["validate", str(duplicate_path)])
    assert duplicate.exit_code == _CLI_CONTRACT_ERROR
    assert "request_id" not in duplicate.output
    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(
        canonical_json_bytes(
            build_request(accepted_controls=False).model_dump(mode="json"),
        )
    )
    denied = runner.invoke(m0708_app, ["publish", str(denied_path)])
    assert denied.exit_code == _CLI_AUTH_ERROR


def test_api_verify_maps_tampering_to_conflict() -> None:
    client = TestClient(create_m0708_app())
    result = client.post(
        "/v1/m07-08/evidence/publish",
        json=build_request().model_dump(mode="json"),
    ).json()
    result["abstention_reason"] = "replay differs"
    result["result_digest"] = result_payload_digest(result)
    tamper = client.post("/v1/m07-08/evidence/verify", json=result)
    assert tamper.status_code == HTTPStatus.CONFLICT
    invalid = client.post("/v1/m07-08/evidence/verify", json={"result_id": "bad"})
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

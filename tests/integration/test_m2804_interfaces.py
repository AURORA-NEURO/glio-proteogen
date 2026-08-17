"""Strict FastAPI, Typer, and SDK parity tests for M28-04."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m28_04 import AuthorizationDecision, contract_json_schemas
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c13_proteotype.m28_04_api_sdk_cli_gateway.api import create_app
from glio_proteogen.modules.c13_proteotype.m28_04_api_sdk_cli_gateway.cli import app
from glio_proteogen.modules.c13_proteotype.m28_04_api_sdk_cli_gateway.sdk import M2804Client
from tests.runtime.test_m2804_runtime import _request

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_CONTENT = 422


def test_api_schema_validate_publish_verify_and_sanitized_errors() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    with TestClient(create_app()) as client:
        schemas = client.get("/v1/modules/M28-04/schemas")
        schema = client.get("/v1/modules/M28-04/schemas/request")
        validated = client.post("/v1/modules/M28-04/validate", json=payload)
        published = client.post("/v1/modules/M28-04/publish", json=payload)
        verified = client.post("/v1/modules/M28-04/verify", json=published.json())
        malformed = client.post("/v1/modules/M28-04/publish", content=b"{not-json")
        unknown = client.get("/v1/modules/M28-04/schemas/unknown")

    assert schemas.status_code == HTTP_OK
    assert set(schemas.json()) == set(contract_json_schemas())
    assert schema.status_code == HTTP_OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert validated.status_code == HTTP_OK
    assert published.status_code == HTTP_OK
    assert verified.status_code == HTTP_OK
    assert verified.json()["verified"] is True
    assert malformed.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert "Traceback" not in malformed.text
    assert unknown.status_code == HTTP_NOT_FOUND


def test_api_rejects_duplicate_json_keys_unknown_claim_and_tampered_result() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    duplicate = b'{"request_id":"first","request_id":"second"}'
    with TestClient(create_app()) as client:
        duplicate_response = client.post("/v1/modules/M28-04/validate", content=duplicate)
        claim = dict(payload)
        claim["unknown_claim"] = True
        claim_response = client.post("/v1/modules/M28-04/validate", json=claim)
        published = client.post("/v1/modules/M28-04/publish", json=payload).json()
        tampered = dict(published)
        tampered["result_id"] = "gateway.m2804.forged"
        invalid = client.post("/v1/modules/M28-04/verify", json=tampered)

    assert duplicate_response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert claim_response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert invalid.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_api_validation_sanitizes_authorization_failure() -> None:
    request = _request()
    rejected = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": rejected})
    payload = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    ).model_dump(mode="json")
    with TestClient(create_app()) as client:
        validated = client.post("/v1/modules/M28-04/validate", json=payload)
        published = client.post("/v1/modules/M28-04/publish", json=payload)

    assert validated.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert published.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert "Traceback" not in validated.text + published.text


def test_cli_schema_validate_publish_verify_and_no_overwrite(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    schema_path = tmp_path / "request-schema.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    exported = runner.invoke(app, ["export-schema", "request", "--output", str(schema_path)])
    validated = runner.invoke(app, ["validate", str(request_path)])
    published = runner.invoke(app, ["publish", str(request_path), "--output", str(result_path)])
    verified = runner.invoke(app, ["verify", str(result_path)])
    overwrite = runner.invoke(app, ["export-schema", "request", "--output", str(schema_path)])

    assert exported.exit_code == 0, exported.output
    assert validated.exit_code == 0, validated.output
    assert published.exit_code == 0, published.output
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.output)["verified"] is True
    assert overwrite.exit_code != 0
    assert "Traceback" not in overwrite.output


def test_cli_rejects_bad_input_and_abstained_publish(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    denied_path = tmp_path / "denied.json"
    bad_path = tmp_path / "bad.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    denied = request.model_copy(
        update={
            "authorizations": (
                request.authorizations[0].model_copy(
                    update={"decision": AuthorizationDecision.DENY}
                ),
            )
        }
    )
    denied_path.write_text(denied.model_dump_json(), encoding="utf-8")
    bad_path.write_text("not-json", encoding="utf-8")
    runner = CliRunner()

    unknown = runner.invoke(app, ["export-schema", "unknown"])
    bad_validate = runner.invoke(app, ["validate", str(bad_path)])
    abstained = runner.invoke(app, ["publish", str(denied_path)])

    assert unknown.exit_code != 0
    assert bad_validate.exit_code != 0
    assert abstained.exit_code == 1
    assert "Traceback" not in unknown.output + bad_validate.output


def test_sdk_uses_the_same_canonical_service_boundary() -> None:
    request = _request()
    client = M2804Client()
    sdk_result = client.publish(request)
    assert client.verify(sdk_result) == sdk_result
    assert client.publish_json(request) == sdk_result.model_dump(mode="json")

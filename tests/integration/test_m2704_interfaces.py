"""Strict FastAPI, Typer, and SDK parity tests for M27-04."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from starlette.requests import Request
from typer.testing import CliRunner

from glio_proteogen.contracts.m27_04 import AuthorizationDecision, contract_json_schemas
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway import api as m2704_api
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.api import create_app
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.cli import app
from glio_proteogen.modules.c20_biomarker_panel.m27_04_api_sdk_cli_gateway.sdk import M2704Client
from tests.runtime.test_m2704_runtime import _request

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_CONTENT = 422


def test_api_schema_validate_publish_verify_and_sanitized_errors() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    with TestClient(create_app()) as client:
        schemas = client.get("/v1/modules/M27-04/schemas")
        schema = client.get("/v1/modules/M27-04/schemas/request")
        validated = client.post("/v1/modules/M27-04/validate", json=payload)
        published = client.post("/v1/modules/M27-04/publish", json=payload)
        verified = client.post("/v1/modules/M27-04/verify", json=published.json())
        malformed = client.post("/v1/modules/M27-04/publish", content=b"{not-json")
        unknown = client.get("/v1/modules/M27-04/schemas/unknown")

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


def test_api_rejects_duplicate_json_keys_and_true_async_claims() -> None:
    request = _request().model_dump(mode="json")
    duplicate = b'{"request_id":"first","request_id":"second"}'
    with TestClient(create_app()) as client:
        duplicate_response = client.post("/v1/modules/M27-04/validate", content=duplicate)
        claim = dict(request)
        claim["unknown_claim"] = True
        claim_response = client.post("/v1/modules/M27-04/validate", json=claim)

    assert duplicate_response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert claim_response.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_api_streams_bounded_bodies_and_applies_result_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()

    def forbidden_body(_request: Request) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Request, "body", forbidden_body)
    monkeypatch.setattr(m2704_api, "M2704_MAX_CANONICAL_RESULT_BYTES", 4)
    with TestClient(create_app()) as client:
        published = client.post(
            "/v1/modules/M27-04/publish",
            content=request.model_dump_json().encode(),
        )
        oversized_result = client.post("/v1/modules/M27-04/verify", content=b'{"x":1}')

    assert published.status_code == HTTP_OK
    assert oversized_result.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_api_verify_rejects_non_object_and_tampered_envelopes() -> None:
    request = _request()
    result = create_app()
    with TestClient(result) as client:
        published = client.post(
            "/v1/modules/M27-04/publish",
            json=request.model_dump(mode="json"),
        ).json()
        non_object = client.post("/v1/modules/M27-04/verify", content=b"[]")
        tampered = dict(published)
        tampered["result_id"] = "gateway.m2704.forged"
        invalid = client.post("/v1/modules/M27-04/verify", json=tampered)

    assert non_object.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert invalid.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_api_validation_and_publish_sanitize_authorization_failures() -> None:
    request = _request()
    rejected = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": rejected})
    payload = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    ).model_dump(mode="json")
    with TestClient(create_app()) as client:
        validated = client.post("/v1/modules/M27-04/validate", json=payload)
        published = client.post("/v1/modules/M27-04/publish", json=payload)

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


def test_cli_rejects_unknown_schema_bad_input_and_abstained_publish(tmp_path: Path) -> None:
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


def test_cli_rejects_authorization_failure_and_tampered_result(tmp_path: Path) -> None:
    request = _request()
    rejected = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": rejected})
    invalid_request = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    invalid_path = tmp_path / "invalid-request.json"
    result_path = tmp_path / "result.json"
    tampered_path = tmp_path / "tampered-result.json"
    invalid_path.write_text(invalid_request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    invalid_publish = runner.invoke(app, ["publish", str(invalid_path)])
    valid_publish = runner.invoke(
        app, ["publish", str(_write_json(tmp_path, request)), "--output", str(result_path)]
    )
    tampered = json.loads(result_path.read_text(encoding="utf-8"))
    tampered["result_id"] = "gateway.m2704.forged"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    invalid_verify = runner.invoke(app, ["verify", str(tampered_path)])

    assert invalid_publish.exit_code != 0
    assert valid_publish.exit_code == 0, valid_publish.output
    assert invalid_verify.exit_code != 0
    assert "Traceback" not in invalid_publish.output + invalid_verify.output


def _write_json(tmp_path: Path, request: object) -> Path:
    path = tmp_path / "valid-request.json"
    path.write_text(request.model_dump_json(), encoding="utf-8")  # type: ignore[attr-defined]
    return path


def test_sdk_and_plugin_use_the_same_canonical_service_boundary() -> None:
    request = _request()
    client = M2704Client()
    sdk_result = client.publish(request)
    assert client.verify(sdk_result) == sdk_result
    assert client.publish_json(request) == sdk_result.model_dump(mode="json")

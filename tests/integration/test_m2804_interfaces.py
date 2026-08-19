"""Strict FastAPI, Typer, and SDK parity tests for M28-04."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m28_04 import (
    M2804_MAX_CANONICAL_REQUEST_BYTES,
    M2804_MAX_CANONICAL_RESULT_BYTES,
    AuthorizationDecision,
    contract_json_schemas,
    result_payload_digest,
)
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c13_proteotype.m28_04_api_sdk_cli_gateway.api import create_app
from glio_proteogen.modules.c13_proteotype.m28_04_api_sdk_cli_gateway.cli import _read_bounded, app
from glio_proteogen.modules.c13_proteotype.m28_04_api_sdk_cli_gateway.sdk import M2804Client
from tests.runtime.test_m2804_runtime import _request

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
        malformed_verify = client.post("/v1/modules/M28-04/verify", content=b"not-json")
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
    assert malformed_verify.status_code == HTTP_UNPROCESSABLE_CONTENT
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


def test_api_verify_requires_object_and_valid_result() -> None:
    request = _request()
    with TestClient(create_app()) as client:
        non_object = client.post("/v1/modules/M28-04/verify", content=b"[]")
        malformed = client.post("/v1/modules/M28-04/verify", json={"result": {}})
        published = client.post(
            "/v1/modules/M28-04/publish", json=request.model_dump(mode="json")
        ).json()
        wrapped = client.post("/v1/modules/M28-04/verify", json={"result": published})
    assert non_object.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert malformed.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert wrapped.status_code == HTTP_OK


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


def test_cli_rejects_invalid_result_and_supports_stdout_schema(tmp_path: Path) -> None:
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("not-json", encoding="utf-8")
    runner = CliRunner()
    schema = runner.invoke(app, ["export-schema", "output"])
    invalid = runner.invoke(app, ["verify", str(bad_result)])
    assert schema.exit_code == 0
    assert '"x-glio-contract"' in schema.output
    assert invalid.exit_code != 0
    assert "Traceback" not in invalid.output


def test_sdk_uses_the_same_canonical_service_boundary() -> None:
    request = _request()
    client = M2804Client()
    sdk_result = client.publish(request)
    assert client.verify(sdk_result) == sdk_result
    assert client.publish_json(request) == sdk_result.model_dump(mode="json")


def test_cli_rejects_oversized_request_and_result_before_parse(tmp_path: Path) -> None:
    oversized_request = tmp_path / "oversized-request.json"
    oversized_result = tmp_path / "oversized-result.json"
    oversized_request.write_bytes(b"{" + b"a" * M2804_MAX_CANONICAL_REQUEST_BYTES + b"}")
    oversized_result.write_bytes(b"{" + b"a" * M2804_MAX_CANONICAL_RESULT_BYTES + b"}")
    runner = CliRunner()

    request_result = runner.invoke(app, ["validate", str(oversized_request)])
    result_result = runner.invoke(app, ["verify", str(oversized_result)])

    assert request_result.exit_code != 0
    assert result_result.exit_code != 0
    assert "Traceback" not in request_result.output
    assert "Traceback" not in result_result.output


def test_cli_bounded_reader_avoids_unbounded_path_read_bytes(tmp_path: Path) -> None:
    path = tmp_path / "bounded.json"
    path.write_bytes(b"{}")
    with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded read")):
        assert _read_bounded(path, max_bytes=2) == b"{}"


def test_cli_bounded_reader_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot be read"):
        _read_bounded(tmp_path / "missing.json", max_bytes=2)


def test_cli_sanitizes_service_rejection_and_replay_mismatch(tmp_path: Path) -> None:
    request = _request()
    rejected = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    rejected_request = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"support": rejected}
                    )
                }
            )
        }
    )
    rejected_path = tmp_path / "rejected.json"
    rejected_path.write_text(rejected_request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    rejected_result = runner.invoke(app, ["publish", str(rejected_path)])
    assert rejected_result.exit_code != 0
    assert "Traceback" not in rejected_result.output

    result = M2804Client().publish(request)
    tampered_model = result.model_copy(update={"findings": ()})
    tampered = tampered_model.model_dump(mode="json")
    tampered["result_digest"] = result_payload_digest(tampered_model)
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    replay_result = runner.invoke(app, ["verify", str(tampered_path)])
    assert replay_result.exit_code != 0
    assert "Traceback" not in replay_result.output

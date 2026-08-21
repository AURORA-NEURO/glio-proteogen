"""Adversarial adapter coverage for M10-08."""

import json

import pytest
import typer
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1008 import _cli_error, create_m1008_app, m1008_app
from glio_proteogen.contracts.m10_08 import result_payload_digest
from tests.modules.c10_pathway_proteotype_factors.test_m10_08_runtime import _request

HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
HTTP_NOT_FOUND = 404
HTTP_REQUEST_TOO_LARGE = 413
CLI_INVALID = 2
CLI_REPLAY_FAILURE = 1


def test_api_rejects_invalid_json_nonfinite_and_bad_contract() -> None:
    client = TestClient(create_m1008_app())
    invalid_json = client.post(
        "/v1/m10-08/validate",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert invalid_json.status_code == HTTP_BAD_REQUEST
    nonfinite = client.post(
        "/v1/m10-08/validate",
        content=b'{"value":NaN}',
        headers={"content-type": "application/json"},
    )
    assert nonfinite.status_code == HTTP_BAD_REQUEST
    bad_contract = client.post("/v1/m10-08/validate", json={"request_id": "missing"})
    assert bad_contract.status_code == HTTP_FORBIDDEN
    malformed_result = client.post(
        "/v1/m10-08/verify",
        json={"result_digest": "sha256:" + "a" * 64},
    )
    assert malformed_result.status_code == HTTP_CONFLICT
    structurally_bad = {"result_digest": result_payload_digest({"result_digest": "placeholder"})}
    malformed_contract = client.post("/v1/m10-08/verify", json=structurally_bad)
    assert malformed_contract.status_code == HTTP_UNPROCESSABLE
    bad_schema = client.get("/v1/m10-08/schema/unknown")
    assert bad_schema.status_code == HTTP_UNPROCESSABLE


def test_api_result_boundary_uses_result_limit_and_rejects_oversize_body() -> None:
    client = TestClient(create_m1008_app())
    oversized = b'{"result_digest":"' + (b"a" * (8 * 1024 * 1024 + 1)) + b'"}'
    response = client.post(
        "/v1/m10-08/verify",
        content=oversized,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTP_REQUEST_TOO_LARGE


def test_cli_publish_verify_replay_and_sanitized_failures() -> None:
    runner = CliRunner()
    request_json = _request().model_dump_json()
    published = runner.invoke(m1008_app, ["publish", "-"], input=request_json)
    assert published.exit_code == 0
    result_payload = json.loads(published.stdout)
    verified = runner.invoke(m1008_app, ["verify", "-"], input=published.stdout)
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True
    result_payload["result_digest"] = "sha256:" + ("b" * 64)
    tampered = runner.invoke(m1008_app, ["verify", "-"], input=json.dumps(result_payload))
    assert tampered.exit_code == CLI_REPLAY_FAILURE
    invalid = runner.invoke(m1008_app, ["validate", "-"], input='{"request_id":"missing"}')
    assert invalid.exit_code == CLI_INVALID
    assert "authorization_failed" in invalid.stderr
    syntax = runner.invoke(m1008_app, ["validate", "-"], input="not-json")
    assert syntax.exit_code == CLI_INVALID
    missing_file = runner.invoke(m1008_app, ["validate", "does-not-exist.json"])
    assert missing_file.exit_code == CLI_INVALID


def test_cli_error_fallback_is_sanitized_and_nonzero() -> None:
    with pytest.raises(typer.Exit) as raised:
        _cli_error(ValueError("sensitive payload"))
    assert raised.value.exit_code == CLI_INVALID

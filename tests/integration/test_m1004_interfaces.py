"""API/CLI parity tests for the provisional M10-04 boundary."""

# Test status and exit code literals make expected transport behavior explicit.
# ruff: noqa: PLR2004

import json

from evals.m10_04.run import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1004 import create_m1004_app, m1004_app


def test_api_schema_and_validation_are_strict() -> None:
    request = build_request().model_dump(mode="json")
    with TestClient(create_m1004_app()) as client:
        schema = client.get("/v1/m10-04/schema/request")
        valid = client.post("/v1/m10-04/validate", json=request)
        duplicate = client.post(
            "/v1/m10-04/validate", content=b'{"request_id":"a","request_id":"b"}'
        )
    assert schema.status_code == 200
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert valid.status_code == 200
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"]["type"] == "json_duplicate_key"


def test_api_estimate_and_verify_round_trip() -> None:
    request = build_request().model_dump(mode="json")
    with TestClient(create_m1004_app()) as client:
        estimated = client.post("/v1/m10-04/estimate", json=request)
        verified = client.post("/v1/m10-04/verify", json=estimated.json())
        tampered = dict(estimated.json(), abstention_reason="tampered")
        rejected = client.post("/v1/m10-04/verify", json=tampered)
    assert estimated.status_code == 200
    assert estimated.json()["status"] == "abstained"
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    assert rejected.status_code == 409
    assert "request" not in rejected.text.lower()


def test_api_sanitizes_contract_errors_and_unknown_schema() -> None:
    with TestClient(create_m1004_app()) as client:
        invalid = client.post("/v1/m10-04/validate", json={"request_id": "secret-value"})
        unknown = client.get("/v1/m10-04/schema/not-a-contract")
    assert invalid.status_code == 422
    assert "secret-value" not in invalid.text
    assert unknown.status_code == 404


def test_cli_validate_estimate_verify_and_schema(tmp_path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    valid = runner.invoke(m1004_app, ["validate", str(request_path)])
    estimated = runner.invoke(m1004_app, ["estimate", str(request_path)])
    result_path = tmp_path / "result.json"
    result_path.write_text(estimated.stdout, encoding="utf-8")
    verified = runner.invoke(m1004_app, ["verify", str(result_path)])
    schema = runner.invoke(m1004_app, ["export-schema", "output"])
    assert valid.exit_code == 0
    assert estimated.exit_code == 0
    assert json.loads(estimated.stdout)["status"] == "abstained"
    assert verified.exit_code == 0
    assert json.loads(schema.stdout)["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_cli_rejects_duplicate_json_without_echoing_payload(tmp_path) -> None:
    request_path = tmp_path / "duplicate.json"
    request_path.write_text('{"request_id":"sensitive","request_id":"other"}', encoding="utf-8")
    result = CliRunner().invoke(m1004_app, ["validate", str(request_path)])
    assert result.exit_code == 2
    assert "sensitive" not in result.output
    assert "other" not in result.output


def test_api_maps_authorization_and_strict_verify_errors() -> None:
    request = build_request(accepted_controls=False).model_dump(mode="json")
    with TestClient(create_m1004_app()) as client:
        denied = client.post("/v1/m10-04/estimate", json=request)
        malformed = client.post("/v1/m10-04/estimate", content=b"not-json")
        duplicate = client.post(
            "/v1/m10-04/verify", content=b'{"result_digest":"a","result_digest":"b"}'
        )
    assert denied.status_code == 403
    assert malformed.status_code == 400
    assert duplicate.status_code == 400


def test_cli_maps_authorization_and_tamper_errors(tmp_path) -> None:
    denied_path = tmp_path / "denied.json"
    denied_path.write_text(
        build_request(accepted_controls=False).model_dump_json(), encoding="utf-8"
    )
    denied = CliRunner().invoke(m1004_app, ["estimate", str(denied_path)])
    assert denied.exit_code == 2
    assert "caller controls" in denied.output
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("not-json", encoding="utf-8")
    malformed = CliRunner().invoke(m1004_app, ["validate", str(malformed_path)])
    assert malformed.exit_code == 2

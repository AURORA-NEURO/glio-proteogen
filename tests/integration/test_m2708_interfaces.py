"""M27-08 API/CLI/plugin interface parity smoke tests."""

# Interface tests intentionally assert protocol status codes and schema counts.
# ruff: noqa: PLR2004, PT018

import json
from pathlib import Path

from evals.m27_08.fixture import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c27_complex_activity.m27_08_retirement.api import create_app
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement.cli import cli
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement.service import M2708Service


def test_schema_routes_and_validate_route() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/contracts/M27-08/schema")
    assert response.status_code == 200
    assert len(response.json()) == 10
    validated = client.post(
        "/v1/modules/M27-08/validate", json=build_request().model_dump(mode="json")
    )
    assert validated.status_code == 200


def test_retire_and_verify_routes_round_trip() -> None:
    client = TestClient(create_app())
    retired = client.post("/v1/modules/M27-08/retire", json=build_request().model_dump(mode="json"))
    assert retired.status_code == 200
    verified = client.post(
        "/v1/modules/M27-08/verify",
        content=json.dumps(retired.json()).encode(),
        headers={"content-type": "application/json"},
    )
    assert verified.status_code == 200
    assert verified.json() == {"verified": True}


def test_invalid_json_is_sanitized() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/v1/modules/M27-08/retire", content=b"[]", headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert "request validation failed" in response.json()["detail"]


def test_service_api_digest_parity() -> None:
    request = build_request()
    local = M2708Service().execute(request)
    api = TestClient(create_app()).post(
        "/v1/modules/M27-08/retire", json=request.model_dump(mode="json")
    )
    assert api.json()["result_digest"] == local.result_digest


def test_cli_validate_retire_export_and_verify(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    schema_path = tmp_path / "schema.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    validated = runner.invoke(cli, ["validate", str(request_path)])
    assert validated.exit_code == 0
    exported = runner.invoke(cli, ["export-schema", "request", "--output", str(schema_path)])
    assert exported.exit_code == 0 and schema_path.exists()
    retired = runner.invoke(cli, ["retire", str(request_path), "--output", str(result_path)])
    assert retired.exit_code == 0 and result_path.exists()
    verified = runner.invoke(cli, ["verify", str(result_path)])
    assert verified.exit_code == 0 and '"verified": true' in verified.stdout


def test_api_denies_unknown_schema_and_invalid_control() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/contracts/M27-08/nope/schema").status_code == 404
    payload = build_request().model_dump(mode="json")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    response = client.post("/v1/modules/M27-08/retire", json=payload)
    assert response.status_code == 422


def test_api_malformed_and_unknown_payloads_are_sanitized() -> None:
    client = TestClient(create_app())
    assert client.post("/v1/modules/M27-08/validate", content=b"not-json").status_code == 422
    invalid = build_request().model_dump(mode="json")
    invalid["unknown"] = "canary"
    response = client.post("/v1/modules/M27-08/validate", json=invalid)
    assert response.status_code == 422
    assert client.post("/v1/modules/M27-08/verify", content=b"{}").status_code == 422


def test_cli_error_paths_are_non_destructive(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli, ["export-schema", "unknown"]).exit_code != 0
    existing = tmp_path / "existing.json"
    existing.write_text("keep", encoding="utf-8")
    assert (
        runner.invoke(cli, ["export-schema", "request", "--output", str(existing)]).exit_code != 0
    )
    assert runner.invoke(cli, ["validate", str(tmp_path / "missing.json")]).exit_code != 0
    assert (
        runner.invoke(cli, ["retire", str(request_path), "--output", str(existing)]).exit_code != 0
    )
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("{}", encoding="utf-8")
    assert runner.invoke(cli, ["verify", str(bad_result)]).exit_code != 0


def test_cli_stdout_and_tamper_paths(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli, ["export-schema", "request"]).exit_code == 0
    assert runner.invoke(cli, ["retire", str(request_path)]).exit_code == 0
    result = M2708Service().execute(build_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "0" * 64
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(result), encoding="utf-8")
    assert runner.invoke(cli, ["verify", str(tampered)]).exit_code != 0

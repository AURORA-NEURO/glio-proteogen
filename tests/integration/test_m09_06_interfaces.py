"""FastAPI, CLI, and plugin parity tests for M09-06."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_06_uncertainty_decomposition_engine as m0906_module,
)
from tests.modules.c09_complex_stoichiometry.test_m09_06_uncertainty import _request

m0906_api = m0906_module.api
m0906_cli = m0906_module.cli

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_FORBIDDEN = 403

if TYPE_CHECKING:
    from pathlib import Path


def test_api_validate_execute_verify_and_schema() -> None:
    payload = _request().model_dump(mode="json")
    with TestClient(m0906_api.create_app()) as client:
        schema = client.get("/v1/modules/M09-06/schemas/output")
        validated = client.post("/v1/modules/M09-06/validate", json=payload)
        executed = client.post("/v1/modules/M09-06/execute", json=payload)
        body = executed.json()
        verified = client.post(
            "/v1/modules/M09-06/verify",
            json={"result": body["result"], "canonical": body["canonical"]},
        )
    assert schema.status_code == HTTP_OK
    assert schema.json()["x-glio-contract"]["sevenUncertaintyDimensionsRequired"] is True
    assert validated.status_code == HTTP_OK
    assert executed.status_code == HTTP_OK
    assert verified.status_code == HTTP_OK
    assert verified.json()["verified"] is True


def test_api_sanitizes_invalid_and_duplicate_json() -> None:
    with TestClient(m0906_api.create_app()) as client:
        invalid = client.post("/v1/modules/M09-06/validate", json={"request_id": "bad"})
        duplicate = client.post(
            "/v1/modules/M09-06/validate",
            content=b'{"request_id":"one","request_id":"two"}',
            headers={"content-type": "application/json"},
        )
        unknown = client.get("/v1/modules/M09-06/schemas/nope")
    assert invalid.status_code == HTTP_UNPROCESSABLE
    assert duplicate.status_code == HTTP_UNPROCESSABLE
    assert unknown.status_code == HTTP_NOT_FOUND


def test_api_rejects_tampered_and_malformed_replay() -> None:
    payload = _request().model_dump(mode="json")
    with TestClient(m0906_api.create_app()) as client:
        executed = client.post("/v1/modules/M09-06/execute", json=payload).json()
        tampered = client.post(
            "/v1/modules/M09-06/verify",
            json={"result": executed["result"], "canonical": executed["canonical"] + " "},
        )
        malformed = client.post("/v1/modules/M09-06/verify", json=[])
    assert tampered.status_code == HTTP_UNPROCESSABLE
    assert tampered.json()["verified"] is False
    assert malformed.status_code == HTTP_UNPROCESSABLE


def test_api_rejects_authorization_and_invalid_replay_envelope() -> None:
    payload = _request().model_dump(mode="json")
    payload["context"]["references"]["quality"]["state"] = "rejected"
    with TestClient(m0906_api.create_app()) as client:
        denied = client.post("/v1/modules/M09-06/validate", json=payload)
        missing = client.post("/v1/modules/M09-06/verify", json={})
        non_object = client.post("/v1/modules/M09-06/verify", json=[])
    assert denied.status_code == HTTP_FORBIDDEN
    assert missing.status_code == HTTP_UNPROCESSABLE
    assert non_object.status_code == HTTP_UNPROCESSABLE


def test_api_execute_maps_service_input_error() -> None:
    class RejectingService(m0906_module.M0906Service):
        def execute(self, _request: object) -> object:
            raise m0906_module.engine.M0906InputError("result_limit")

    with TestClient(m0906_api.create_app(RejectingService())) as client:
        response = client.post(
            "/v1/modules/M09-06/execute",
            json=_request().model_dump(mode="json"),
        )
    assert response.status_code == HTTP_UNPROCESSABLE


def test_cli_validate_execute_verify_and_no_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    canonical_path = tmp_path / "canonical.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(m0906_cli.app, ["validate", str(request_path)]).exit_code == 0
    executed = runner.invoke(
        m0906_cli.app,
        ["execute", str(request_path), "--output", str(result_path)],
    )
    repeated = runner.invoke(
        m0906_cli.app,
        ["execute", str(request_path), "--output", str(result_path)],
    )
    canonical_path.write_bytes(result_path.read_bytes())
    verified = runner.invoke(
        m0906_cli.app,
        ["verify", str(result_path), str(canonical_path)],
    )
    assert executed.exit_code == 0
    assert repeated.exit_code != 0
    assert verified.exit_code == 0


def test_cli_abstention_and_schema_errors(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(_request(method="unsupported:foundation-model").model_dump(mode="json")),
        encoding="utf-8",
    )
    runner = CliRunner()
    abstained = runner.invoke(m0906_cli.app, ["execute", str(request_path)])
    schema = runner.invoke(m0906_cli.app, ["export-schema", "request"])
    unknown = runner.invoke(m0906_cli.app, ["export-schema", "unknown"])
    assert abstained.exit_code == 1
    assert schema.exit_code == 0
    assert unknown.exit_code != 0


def test_cli_rejects_malformed_input_and_tampered_replay(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("[", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(m0906_cli.app, ["validate", str(malformed)]).exit_code != 0
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    assert runner.invoke(m0906_cli.app, ["execute", str(invalid)]).exit_code != 0

    valid = tmp_path / "valid.json"
    result = tmp_path / "result.json"
    canonical = tmp_path / "canonical.json"
    valid.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    assert (
        runner.invoke(
            m0906_cli.app,
            ["execute", str(valid), "--output", str(result)],
        ).exit_code
        == 0
    )
    canonical.write_bytes(result.read_bytes() + b" ")
    assert runner.invoke(m0906_cli.app, ["verify", str(result), str(canonical)]).exit_code != 0

    malformed_result = tmp_path / "malformed-result.json"
    malformed_result.write_text("[", encoding="utf-8")
    assert (
        runner.invoke(
            m0906_cli.app,
            ["verify", str(malformed_result), str(canonical)],
        ).exit_code
        != 0
    )
    list_result = tmp_path / "list-result.json"
    list_result.write_text("[]", encoding="utf-8")
    assert (
        runner.invoke(
            m0906_cli.app,
            ["verify", str(list_result), str(canonical)],
        ).exit_code
        != 0
    )

"""FastAPI, CLI and parse-once parity for provisional M11-08."""

from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path  # noqa: TC003

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1108 import create_m1108_app, m1108_app
from glio_proteogen.modules.c11_protein_native_subtype.m11_08_mechanism_evidence_dossier import (
    M1108MechanismEvidenceDossierPlugin,
    M1108MechanismEvidenceDossierService,
)
from tests.contract.test_m11_08_runtime import request

CLI_ERROR = 2


def test_api_validate_assemble_verify_and_schema() -> None:
    typed = request()
    body = typed.model_dump_json()
    client = TestClient(create_m1108_app())
    schema = client.get("/v1/m11-08/schema/request")
    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["x-glio-contract"]["safeAbstention"] is True
    validated = client.post("/v1/m11-08/validate", content=body)
    assert validated.status_code == HTTPStatus.OK
    assembled = client.post("/v1/modules/M11-08/assemble", content=body)
    assert assembled.status_code == HTTPStatus.OK
    result = assembled.json()
    assert result["status"] == "ready"
    verified = client.post("/v1/m11-08/verify", json=result)
    assert verified.status_code == HTTPStatus.OK
    assert verified.json()["verified"] is True


def test_api_sanitizes_duplicate_and_authorization_errors() -> None:
    typed = request()
    body = typed.model_dump_json()
    duplicate = body[:-1] + ',"request_id":"second"}'
    client = TestClient(create_m1108_app())
    response = client.post("/v1/m11-08/validate", content=duplicate)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "second" not in response.text
    denied = json.loads(body)
    denied["context"]["references"]["consent"]["state"] = "withheld"
    response = client.post("/v1/m11-08/assemble", json=denied)
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "consent" not in response.text


def test_cli_and_plugin_use_same_canonical_operation() -> None:
    body = request().model_dump_json()
    runner = CliRunner()
    validated = runner.invoke(m1108_app, ["validate", "-"], input=body)
    assert validated.exit_code == 0, validated.output
    assembled = runner.invoke(m1108_app, ["assemble", "-"], input=body)
    assert assembled.exit_code == 0, assembled.output
    cli_result = json.loads(assembled.stdout)
    plugin = M1108MechanismEvidenceDossierPlugin(M1108MechanismEvidenceDossierService())
    plugin_result = plugin.run(plugin.validate(body))
    assert cli_result == plugin_result.model_dump(mode="json")
    verified = runner.invoke(m1108_app, ["verify", "-"], input=assembled.stdout)
    assert verified.exit_code == 0, verified.output


def test_api_validation_replay_and_strict_json_failures() -> None:
    typed = request()
    body = json.loads(typed.model_dump_json())
    client = TestClient(create_m1108_app())
    invalid = dict(body)
    invalid.pop("request_id")
    response = client.post("/v1/m11-08/validate", json=invalid)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assembled = client.post("/v1/m11-08/assemble", json=body).json()
    tampered = dict(assembled)
    tampered["result_digest"] = "sha256:" + ("b" * 64)
    response = client.post("/v1/m11-08/verify", json=tampered)
    assert response.status_code == HTTPStatus.CONFLICT
    invalid_result = dict(assembled)
    invalid_result.pop("result_digest")
    response = client.post("/v1/m11-08/verify", json=invalid_result)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    duplicate = typed.model_dump_json()[:-1] + ',"request_id":"second"}'
    response = client.post("/v1/m11-08/assemble", content=duplicate)
    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_api_reports_service_replay_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = TestClient(create_m1108_app())
    result = client.post("/v1/m11-08/assemble", content=request().model_dump_json()).json()
    monkeypatch.setattr(
        "glio_proteogen.adapters.m1108.m1108_runtime.M1108MechanismEvidenceDossierService.verify",
        staticmethod(lambda _result: False),
    )
    response = client.post("/v1/m11-08/verify", json=result)
    assert response.status_code == HTTPStatus.CONFLICT


def test_cli_schema_and_sanitized_error_paths(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    schema = runner.invoke(m1108_app, ["export-schema", "request"])
    assert schema.exit_code == 0
    valid_body = request().model_dump_json()
    denied = json.loads(valid_body)
    denied["context"]["references"]["consent"]["state"] = "withheld"
    denied_path = tmp_path / "denied.json"
    denied_path.write_text(json.dumps(denied), encoding="utf-8")
    denied_result = runner.invoke(m1108_app, ["validate", str(denied_path)])
    assert denied_result.exit_code == CLI_ERROR
    invalid = json.loads(valid_body)
    invalid.pop("request_id")
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
    invalid_result = runner.invoke(m1108_app, ["assemble", str(invalid_path)])
    assert invalid_result.exit_code == CLI_ERROR
    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"request_id":', encoding="utf-8")
    malformed_result = runner.invoke(m1108_app, ["validate", str(malformed)])
    assert malformed_result.exit_code == CLI_ERROR
    missing_result = runner.invoke(m1108_app, ["validate", str(tmp_path / "missing.json")])
    assert missing_result.exit_code == CLI_ERROR
    assembled = runner.invoke(m1108_app, ["assemble", "-"], input=valid_body)
    tampered_path = tmp_path / "tampered-result.json"
    tampered_payload = json.loads(assembled.stdout)
    tampered_payload["result_digest"] = "sha256:" + ("c" * 64)
    tampered_path.write_text(json.dumps(tampered_payload), encoding="utf-8")
    replay_result = runner.invoke(m1108_app, ["verify", str(tampered_path)])
    assert replay_result.exit_code == 1
    invalid_result_path = tmp_path / "invalid-result.json"
    invalid_result_payload = json.loads(assembled.stdout)
    invalid_result_payload.pop("result_digest")
    invalid_result_path.write_text(json.dumps(invalid_result_payload), encoding="utf-8")
    invalid_replay = runner.invoke(m1108_app, ["verify", str(invalid_result_path)])
    assert invalid_replay.exit_code == CLI_ERROR
    valid_result_path = tmp_path / "valid-result.json"
    valid_result_path.write_text(assembled.stdout, encoding="utf-8")
    monkeypatch.setattr(
        "glio_proteogen.adapters.m1108.m1108_runtime.M1108MechanismEvidenceDossierService.verify",
        staticmethod(lambda _result: False),
    )
    service_replay = runner.invoke(m1108_app, ["verify", str(valid_result_path)])
    assert service_replay.exit_code == 1

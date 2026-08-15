"""FastAPI, CLI and parse-once parity for provisional M11-08."""

from __future__ import annotations

import json
from http import HTTPStatus

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1108 import create_m1108_app, m1108_app
from glio_proteogen.modules.c11_protein_native_subtype.m11_08_mechanism_evidence_dossier import (
    M1108MechanismEvidenceDossierPlugin,
    M1108MechanismEvidenceDossierService,
)
from tests.contract.test_m11_08_runtime import request


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

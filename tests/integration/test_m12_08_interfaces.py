"""FastAPI and Typer parity tests for M12-08."""

# ruff: noqa: PLR2004

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.adapters.m1208 as adapter_module
from glio_proteogen.adapters.m1208 import app, m1208_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c12_driver_to_protein_consequence.m12_08_mechanism_evidence_dossier import (  # noqa: E501
    M1208AuthorizationError,
    M1208Service,
)
from tests.contract.test_m12_08_deep import _request

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_fastapi_invalid_json_validation_and_replay_errors() -> None:
    client = TestClient(app)
    assert (
        client.post(
            "/v1/modules/M12-08/mechanism-dossier",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/modules/M12-08/mechanism-dossier",
            content=b"{}",
            headers={"content-type": "application/json"},
        ).status_code
        == 403
    )
    result = M1208Service().execute(_request()).model_dump(mode="json")
    tampered = dict(result)
    tampered["result_digest"] = "sha256:" + "a" * 64
    response = client.post("/v1/modules/M12-08/verify", json=tampered)
    assert response.status_code == 422
    assert (
        client.post(
            "/v1/modules/M12-08/verify", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )
    invalid_request = _request().model_dump(mode="json")
    invalid_request.pop("request_id")
    assert (
        client.post("/v1/modules/M12-08/mechanism-dossier", json=invalid_request).status_code == 422
    )


def test_fastapi_service_authorization_error_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AuthorizationService:
        def _execute_validated(self, _request: object) -> object:
            raise M1208AuthorizationError

    monkeypatch.setattr(adapter_module, "_SERVICE", AuthorizationService())
    response = TestClient(app).post(
        "/v1/modules/M12-08/mechanism-dossier", json=_request().model_dump(mode="json")
    )
    assert response.status_code == 403


def test_schema_route_and_typer_assemble_verify_no_overwrite(tmp_path: Path) -> None:
    client = TestClient(app)
    schema = client.get("/v1/m12-08/schema/request")
    assert schema.status_code == 200
    assert schema.json()["$schema"]
    assert client.get("/v1/m12-08/schema/not-real").status_code == 404

    runner = CliRunner()
    schema_result = runner.invoke(m1208_app, ["export-schema", "request"])
    assert schema_result.exit_code == 0
    assert json.loads(schema_result.stdout)["$schema"]
    assert runner.invoke(m1208_app, ["export-schema", "not-real"]).exit_code == 2
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    result_path = tmp_path / "result.json"
    assembled = runner.invoke(
        m1208_app, ["assemble", str(request_path), "--output", str(result_path)]
    )
    assert assembled.exit_code == 0
    assert result_path.exists()
    no_overwrite = runner.invoke(
        m1208_app, ["assemble", str(request_path), "--output", str(result_path)]
    )
    assert no_overwrite.exit_code != 0
    verified = runner.invoke(m1208_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    stdout_assembled = runner.invoke(m1208_app, ["assemble", str(request_path)])
    assert stdout_assembled.exit_code == 0
    assert "ready" in stdout_assembled.stdout
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert runner.invoke(m1208_app, ["assemble", str(invalid)]).exit_code != 0
    assert runner.invoke(m1208_app, ["verify", str(invalid)]).exit_code != 0

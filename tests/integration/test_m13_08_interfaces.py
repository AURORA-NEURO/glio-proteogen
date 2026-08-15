"""FastAPI and Typer parity tests for M13-08."""

# ruff: noqa: PLR2004

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.adapters.m1308 as adapter_module
from glio_proteogen.adapters.m1308 import app, m1308_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c13_variant_peptide.m13_08_mechanism_evidence_dossier import (
    M1308AuthorizationError,
    M1308Service,
)
from tests.contract.test_m13_08_deep import _request

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_fastapi_invalid_json_validation_and_replay_errors() -> None:
    client = TestClient(app)
    assert (
        client.post(
            "/v1/modules/M13-08/dossier",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/modules/M13-08/dossier",
            content=b"{}",
            headers={"content-type": "application/json"},
        ).status_code
        == 403
    )
    result = M1308Service().execute(_request()).model_dump(mode="json")
    tampered = dict(result)
    tampered["result_digest"] = "sha256:" + "a" * 64
    assert client.post("/v1/modules/M13-08/verify", json=tampered).status_code == 422
    assert (
        client.post(
            "/v1/modules/M13-08/verify", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )
    invalid_request = _request().model_dump(mode="json")
    invalid_request.pop("request_id")
    assert client.post("/v1/modules/M13-08/dossier", json=invalid_request).status_code == 422


def test_fastapi_service_authorization_error_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AuthorizationService:
        def _execute_validated(self, _request: object) -> object:
            raise M1308AuthorizationError

    monkeypatch.setattr(adapter_module, "_SERVICE", AuthorizationService())
    response = TestClient(app).post(
        "/v1/modules/M13-08/dossier", json=_request().model_dump(mode="json")
    )
    assert response.status_code == 403


def test_typer_schema_assemble_verify_no_overwrite_and_invalid_files(tmp_path: Path) -> None:
    runner = CliRunner()
    schema = runner.invoke(m1308_app, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["$schema"]
    unknown_schema = runner.invoke(m1308_app, ["export-schema", "not-real"])
    assert unknown_schema.exit_code == 2
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    result_path = tmp_path / "result.json"
    assembled = runner.invoke(
        m1308_app, ["assemble", str(request_path), "--output", str(result_path)]
    )
    assert assembled.exit_code == 0
    assert result_path.exists()
    no_overwrite = runner.invoke(
        m1308_app, ["assemble", str(request_path), "--output", str(result_path)]
    )
    assert no_overwrite.exit_code != 0
    verified = runner.invoke(m1308_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    stdout_assembled = runner.invoke(m1308_app, ["assemble", str(request_path)])
    assert stdout_assembled.exit_code == 0
    assert "ready" in stdout_assembled.stdout
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert runner.invoke(m1308_app, ["assemble", str(invalid)]).exit_code != 0
    assert runner.invoke(m1308_app, ["verify", str(invalid)]).exit_code != 0

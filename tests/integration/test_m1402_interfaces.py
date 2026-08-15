"""FastAPI, Typer, and plugin parity tests for M14-02."""

# ruff: noqa: PLR2004

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves this runtime type.
from typing import cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.adapters.m1402 as adapter_module
from glio_proteogen.adapters.m1402 import app, m1402_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c14_microenvironment.m14_02_context_subtype_stratifier import (
    M1402InferenceError,
    M1402Plugin,
    M1402ReplayVerificationError,
    M1402Service,
    ValidatedM1402Request,
)
from tests.modules.c14_microenvironment.test_m14_02_engine import _request


def test_fastapi_validation_schema_stratify_and_verify_paths() -> None:
    client = TestClient(app)
    assert client.post("/v1/modules/M14-02/stratify", content=b"{}").status_code == 415
    assert client.get("/v1/m14-02/schema/request").status_code == 200
    assert client.get("/v1/m14-02/schema/not-real").status_code == 404
    assert (
        client.post(
            "/v1/modules/M14-02/stratify",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assembled = client.post("/v1/modules/M14-02/stratify", json=_request().model_dump(mode="json"))
    assert assembled.status_code == 200
    result = assembled.json()
    verified = client.post("/v1/modules/M14-02/verify", json=result)
    assert verified.status_code == 200
    assert verified.json() == result
    tampered = dict(result)
    tampered["result_digest"] = "sha256:" + "a" * 64
    assert client.post("/v1/modules/M14-02/verify", json=tampered).status_code == 422
    assert (
        client.post(
            "/v1/modules/M14-02/verify", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )


def test_fastapi_authorization_and_replay_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied = client = TestClient(app)
    response = denied.post(
        "/v1/modules/M14-02/stratify",
        json=_request(accepted=False).model_dump(mode="json"),
    )
    assert response.status_code == 403

    class ReplayService:
        def verify(self, _result: object) -> object:
            raise M1402ReplayVerificationError

    monkeypatch.setattr(adapter_module, "_SERVICE", ReplayService())
    result = M1402Service().execute(_request()).model_dump(mode="json")
    assert client.post("/v1/modules/M14-02/verify", json=result).status_code == 422


def test_typer_stratify_verify_export_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(m1402_app, ["export-schema", "request"]).exit_code == 0
    schema = runner.invoke(m1402_app, ["export-schema", "request"])
    assert json.loads(schema.stdout)["$schema"]
    assert runner.invoke(m1402_app, ["export-schema", "not-real"]).exit_code == 2
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    result_path = tmp_path / "result.json"
    assembled = runner.invoke(
        m1402_app, ["stratify", str(request_path), "--output", str(result_path)]
    )
    assert assembled.exit_code == 0
    assert result_path.exists()
    assert (
        runner.invoke(
            m1402_app, ["stratify", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1402_app, ["verify", str(result_path)]).exit_code == 0
    stdout_result = runner.invoke(m1402_app, ["stratify", str(request_path)])
    assert stdout_result.exit_code == 0
    assert "stratified" in stdout_result.stdout
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert runner.invoke(m1402_app, ["stratify", str(invalid)]).exit_code != 0
    assert runner.invoke(m1402_app, ["verify", str(invalid)]).exit_code != 0


def test_plugin_is_strict_parse_once_and_rejects_forged_capability() -> None:
    plugin = M1402Plugin(M1402Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M14-02"
    token = plugin.validate(_request())
    assert plugin.run(token).status.value == "stratified"
    assert isinstance(token, ValidatedM1402Request)
    forged = ValidatedM1402Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("ValidatedM1402Request", []))
    with pytest.raises(ValueError, match="duplicate"):
        plugin.validate('{"request_id":"a","request_id":"b"}')
    bytes_token = plugin.validate(canonical_json_bytes(_request()))
    assert plugin.run(bytes_token).status.value == "stratified"
    assert plugin.verify(plugin.run(bytes_token)).status.value == "stratified"


def test_fastapi_service_inference_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    class InferenceService:
        def _execute_validated(self, _request: object) -> object:
            raise M1402InferenceError

    monkeypatch.setattr(adapter_module, "_SERVICE", InferenceService())
    response = TestClient(app).post(
        "/v1/modules/M14-02/stratify", json=_request().model_dump(mode="json")
    )
    assert response.status_code == 422

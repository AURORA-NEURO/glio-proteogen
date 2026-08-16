"""FastAPI, Typer, and plugin parity tests for M15-01."""

# ruff: noqa: PLR2004

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves this runtime type.
from typing import cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.adapters.m1501 as adapter_module
from glio_proteogen.adapters.m1501 import app, m1501_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_01_biological_hypothesis_registry import (  # noqa: E501
    M1501AuthorizationError,
    M1501InferenceError,
    M1501Plugin,
    M1501ReplayVerificationError,
    M1501Service,
    ValidatedM1501Request,
)
from tests.modules.c15_longitudinal_recurrence.test_m15_01_engine import _request


def test_fastapi_schema_register_verify_and_strict_error_paths() -> None:
    client = TestClient(app)
    assert client.post("/v1/modules/M15-01/register", content=b"{}").status_code == 415
    assert client.get("/v1/m15-01/schema/request").status_code == 200
    assert client.get("/v1/m15-01/schema/not-real").status_code == 404
    assert (
        client.post(
            "/v1/modules/M15-01/register",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assembled = client.post("/v1/modules/M15-01/register", json=_request().model_dump(mode="json"))
    assert assembled.status_code == 200
    result = assembled.json()
    verified = client.post("/v1/modules/M15-01/verify", json=result)
    assert verified.status_code == 200
    assert verified.json() == result
    tampered = dict(result)
    tampered["result_digest"] = "sha256:" + "a" * 64
    assert client.post("/v1/modules/M15-01/verify", json=tampered).status_code == 422
    assert (
        client.post(
            "/v1/modules/M15-01/verify",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )
    invalid_request = _request().model_dump(mode="json")
    invalid_request.pop("hypotheses")
    assert client.post("/v1/modules/M15-01/register", json=invalid_request).status_code == 422


def test_fastapi_authorization_and_replay_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(accepted=False)
    response = TestClient(app).post(
        "/v1/modules/M15-01/register", json=request.model_dump(mode="json")
    )
    assert response.status_code == 403

    class ReplayService:
        def verify(self, _result: object, *, replay: bool = True) -> object:
            del replay
            raise M1501ReplayVerificationError

    monkeypatch.setattr(adapter_module, "_SERVICE", ReplayService())
    result = M1501Service().execute(_request()).model_dump(mode="json")
    assert TestClient(app).post("/v1/modules/M15-01/verify", json=result).status_code == 422

    class AuthorizationService:
        def _execute_validated(self, _request: object) -> object:
            raise M1501AuthorizationError

    monkeypatch.setattr(adapter_module, "_SERVICE", AuthorizationService())
    assert (
        TestClient(app)
        .post("/v1/modules/M15-01/register", json=_request().model_dump(mode="json"))
        .status_code
        == 403
    )


def test_typer_register_verify_export_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(m1501_app, ["export-schema", "request"]).exit_code == 0
    schema = runner.invoke(m1501_app, ["export-schema", "request"])
    assert json.loads(schema.stdout)["$schema"]
    assert runner.invoke(m1501_app, ["export-schema", "not-real"]).exit_code == 2
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    result_path = tmp_path / "result.json"
    assembled = runner.invoke(
        m1501_app, ["register", str(request_path), "--output", str(result_path)]
    )
    assert assembled.exit_code == 0
    assert result_path.exists()
    assert (
        runner.invoke(
            m1501_app, ["register", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1501_app, ["verify", str(result_path)]).exit_code == 0
    stdout_result = runner.invoke(m1501_app, ["register", str(request_path)])
    assert stdout_result.exit_code == 0
    assert "registered" in stdout_result.stdout or "supported" in stdout_result.stdout
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert runner.invoke(m1501_app, ["register", str(invalid)]).exit_code != 0
    assert runner.invoke(m1501_app, ["verify", str(invalid)]).exit_code != 0


def test_plugin_is_strict_parse_once_and_rejects_forged_capability() -> None:
    plugin = M1501Plugin(M1501Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M15-01"
    token = plugin.validate(_request())
    assert plugin.run(token).status.value == "supported"
    assert isinstance(token, ValidatedM1501Request)
    forged = ValidatedM1501Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("ValidatedM1501Request", []))
    with pytest.raises(ValueError, match="duplicate"):
        plugin.validate('{"request_id":"a","request_id":"b"}')
    bytes_token = plugin.validate(canonical_json_bytes(_request()))
    assert plugin.run(bytes_token).status.value == "supported"
    assert plugin.verify(plugin.run(bytes_token)).status.value == "supported"


def test_fastapi_service_inference_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    class InferenceService:
        def _execute_validated(self, _request: object) -> object:
            raise M1501InferenceError

    monkeypatch.setattr(adapter_module, "_SERVICE", InferenceService())
    response = TestClient(app).post(
        "/v1/modules/M15-01/register", json=_request().model_dump(mode="json")
    )
    assert response.status_code == 422

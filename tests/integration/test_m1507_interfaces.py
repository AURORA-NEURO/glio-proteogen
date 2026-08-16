"""FastAPI, Typer, and plugin parity tests for M15-07."""

# ruff: noqa: E501, PLR2004

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.adapters.m1507 as adapter_module
from glio_proteogen.adapters.m1507 import app, m1507_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c15_longitudinal_recurrence.m15_07_plausibility_negative_control_adjudicator import (
    M1507AuthorizationError,
    M1507InferenceError,
    M1507Plugin,
    M1507ReplayVerificationError,
    M1507Service,
    ValidatedM1507Request,
)
from tests.modules.c15_longitudinal_recurrence.test_m15_07_engine import _request

if TYPE_CHECKING:
    from pathlib import Path


def test_fastapi_schema_adjudicate_verify_and_strict_error_paths() -> None:
    client = TestClient(app)
    assert client.post("/v1/modules/M15-07/adjudicate", content=b"{}").status_code == 415
    assert client.get("/v1/m15-07/schema/request").status_code == 200
    assert client.get("/v1/m15-07/schema/not-real").status_code == 404
    assert (
        client.post(
            "/v1/modules/M15-07/adjudicate",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assembled = client.post(
        "/v1/modules/M15-07/adjudicate", json=_request().model_dump(mode="json")
    )
    assert assembled.status_code == 200
    result = assembled.json()
    verified = client.post("/v1/modules/M15-07/verify", json=result)
    assert verified.status_code == 200
    assert verified.json() == result
    tampered = dict(result)
    tampered["result_digest"] = "sha256:" + "a" * 64
    assert client.post("/v1/modules/M15-07/verify", json=tampered).status_code == 422
    assert (
        client.post(
            "/v1/modules/M15-07/verify",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )
    invalid_request = _request().model_dump(mode="json")
    invalid_request.pop("controls")
    assert client.post("/v1/modules/M15-07/adjudicate", json=invalid_request).status_code == 422


def test_fastapi_authorization_and_replay_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = TestClient(app).post(
        "/v1/modules/M15-07/adjudicate",
        json=_request().model_dump(mode="json") | {"context": {"references": {}}},
    )
    assert response.status_code == 403

    class ReplayService:
        def verify(self, _result: object, *, replay: bool = True) -> object:
            del replay
            raise M1507ReplayVerificationError

    monkeypatch.setattr(adapter_module, "_SERVICE", ReplayService())
    result = M1507Service().execute(_request()).model_dump(mode="json")
    assert TestClient(app).post("/v1/modules/M15-07/verify", json=result).status_code == 422

    class AuthorizationService:
        def _execute_validated(self, _request: object) -> object:
            raise M1507AuthorizationError

    monkeypatch.setattr(adapter_module, "_SERVICE", AuthorizationService())
    assert (
        TestClient(app)
        .post("/v1/modules/M15-07/adjudicate", json=_request().model_dump(mode="json"))
        .status_code
        == 403
    )


def test_typer_adjudicate_verify_export_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(m1507_app, ["export-schema", "request"]).exit_code == 0
    schema = runner.invoke(m1507_app, ["export-schema", "request"])
    assert json.loads(schema.stdout)["$schema"]
    assert runner.invoke(m1507_app, ["export-schema", "not-real"]).exit_code == 2
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    result_path = tmp_path / "result.json"
    assembled = runner.invoke(
        m1507_app, ["adjudicate", str(request_path), "--output", str(result_path)]
    )
    assert assembled.exit_code == 0
    assert result_path.exists()
    assert (
        runner.invoke(
            m1507_app, ["adjudicate", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1507_app, ["verify", str(result_path)]).exit_code == 0
    stdout_result = runner.invoke(m1507_app, ["adjudicate", str(request_path)])
    assert stdout_result.exit_code == 0
    assert "adjudicated" in stdout_result.stdout
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert runner.invoke(m1507_app, ["adjudicate", str(invalid)]).exit_code != 0
    assert runner.invoke(m1507_app, ["verify", str(invalid)]).exit_code != 0


def test_plugin_is_strict_parse_once_and_rejects_forged_capability() -> None:
    plugin = M1507Plugin(M1507Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M15-07"
    token = plugin.validate(_request())
    assert plugin.run(token).status.value == "adjudicated"
    assert isinstance(token, ValidatedM1507Request)
    forged = ValidatedM1507Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("ValidatedM1507Request", []))
    with pytest.raises(ValueError, match="duplicate"):
        plugin.validate('{"request_id":"a","request_id":"b"}')
    bytes_token = plugin.validate(canonical_json_bytes(_request()))
    assert plugin.run(bytes_token).status.value == "adjudicated"
    assert plugin.verify(plugin.run(bytes_token)).status.value == "adjudicated"


def test_fastapi_inference_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    class InferenceService:
        def _execute_validated(self, _request: object) -> object:
            raise M1507InferenceError

    monkeypatch.setattr(adapter_module, "_SERVICE", InferenceService())
    response = TestClient(app).post(
        "/v1/modules/M15-07/adjudicate", json=_request().model_dump(mode="json")
    )
    assert response.status_code == 422

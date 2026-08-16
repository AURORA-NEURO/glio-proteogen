"""FastAPI, Typer, and plugin parity tests for M16-07."""

# ruff: noqa: PLR2004

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.adapters.m1607 as adapter_module
from glio_proteogen.adapters.m1607 import app, m1607_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_07_downstream_typed_export import (
    M1607AuthorizationError,
    M1607InferenceError,
    M1607Plugin,
    M1607ReplayVerificationError,
    M1607Service,
    ValidatedM1607Request,
)
from tests.modules.c16_kinophos_object_consumer.test_m16_07_engine import _request

if TYPE_CHECKING:
    from pathlib import Path


def test_fastapi_schema_export_verify_and_strict_errors() -> None:
    client = TestClient(app)
    assert client.post("/v1/modules/M16-07/export", content=b"{}").status_code == 415
    assert client.get("/v1/m16-07/schema/request").status_code == 200
    assert client.get("/v1/m16-07/schema/not-real").status_code == 404
    assert (
        client.post(
            "/v1/modules/M16-07/export",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assembled = client.post("/v1/modules/M16-07/export", json=_request().model_dump(mode="json"))
    assert assembled.status_code == 200
    result = assembled.json()
    verified = client.post("/v1/modules/M16-07/verify", json=result)
    assert verified.status_code == 200
    assert verified.json() == result
    tampered = dict(result)
    tampered["result_digest"] = "sha256:" + "a" * 64
    assert client.post("/v1/modules/M16-07/verify", json=tampered).status_code == 422
    assert (
        client.post(
            "/v1/modules/M16-07/verify", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )


def test_fastapi_authorization_replay_and_inference_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied = TestClient(app).post(
        "/v1/modules/M16-07/export",
        json=_request().model_dump(mode="json") | {"context": {"references": {}}},
    )
    assert denied.status_code == 403

    class ReplayService:
        def verify(self, _result: object, *, replay: bool = True) -> object:
            del replay
            raise M1607ReplayVerificationError

    monkeypatch.setattr(adapter_module, "_SERVICE", ReplayService())
    result = M1607Service().execute(_request()).model_dump(mode="json")
    assert TestClient(app).post("/v1/modules/M16-07/verify", json=result).status_code == 422

    class AuthorizationService:
        def _execute_validated(self, _request: object) -> object:
            raise M1607AuthorizationError

    monkeypatch.setattr(adapter_module, "_SERVICE", AuthorizationService())
    assert (
        TestClient(app)
        .post("/v1/modules/M16-07/export", json=_request().model_dump(mode="json"))
        .status_code
        == 403
    )

    class InferenceService:
        def _execute_validated(self, _request: object) -> object:
            raise M1607InferenceError

    monkeypatch.setattr(adapter_module, "_SERVICE", InferenceService())
    assert (
        TestClient(app)
        .post("/v1/modules/M16-07/export", json=_request().model_dump(mode="json"))
        .status_code
        == 422
    )


def test_typer_export_verify_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(m1607_app, ["export-schema", "request"]).exit_code == 0
    schema = runner.invoke(m1607_app, ["export-schema", "request"])
    assert json.loads(schema.stdout)["$schema"]
    assert runner.invoke(m1607_app, ["export-schema", "not-real"]).exit_code == 2
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    result_path = tmp_path / "result.json"
    assembled = runner.invoke(
        m1607_app, ["export", str(request_path), "--output", str(result_path)]
    )
    assert assembled.exit_code == 0
    assert result_path.exists()
    assert (
        runner.invoke(
            m1607_app, ["export", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1607_app, ["verify", str(result_path)]).exit_code == 0
    stdout_result = runner.invoke(m1607_app, ["export", str(request_path)])
    assert stdout_result.exit_code == 0
    assert "signed" in stdout_result.stdout
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert runner.invoke(m1607_app, ["export", str(invalid)]).exit_code != 0
    assert runner.invoke(m1607_app, ["verify", str(invalid)]).exit_code != 0


def test_plugin_strict_parse_once_and_forged_capability_rejection() -> None:
    plugin = M1607Plugin(M1607Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M16-07"
    token = plugin.validate(_request())
    assert plugin.run(token).status.value == "signed"
    assert isinstance(token, ValidatedM1607Request)
    forged = ValidatedM1607Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("ValidatedM1607Request", []))
    with pytest.raises(ValueError, match="duplicate"):
        plugin.validate('{"request_id":"a","request_id":"b"}')
    bytes_token = plugin.validate(canonical_json_bytes(_request()))
    assert plugin.run(bytes_token).status.value == "signed"
    assert plugin.verify(plugin.run(bytes_token)).status.value == "signed"

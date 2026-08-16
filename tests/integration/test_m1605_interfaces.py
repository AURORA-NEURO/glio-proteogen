"""FastAPI, Typer, and plugin parity tests for M16-05."""

# ruff: noqa: E501, PLR2004

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.adapters.m1605 as adapter_module
from glio_proteogen.adapters.m1605 import app, m1605_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_05_workflow_presentation_service import (
    M1605AuthorizationError,
    M1605InferenceError,
    M1605Plugin,
    M1605ReplayVerificationError,
    M1605Service,
    ValidatedM1605Request,
)
from tests.modules.c16_kinophos_object_consumer.test_m16_05_engine import _request

if TYPE_CHECKING:
    from pathlib import Path


def test_fastapi_schema_present_verify_and_strict_errors() -> None:
    client = TestClient(app)
    assert client.post("/v1/modules/M16-05/present", content=b"{}").status_code == 415
    assert client.get("/v1/m16-05/schema/request").status_code == 200
    assert client.get("/v1/m16-05/schema/not-real").status_code == 404
    assert (
        client.post(
            "/v1/modules/M16-05/present",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assembled = client.post("/v1/modules/M16-05/present", json=_request().model_dump(mode="json"))
    assert assembled.status_code == 200
    result = assembled.json()
    verified = client.post("/v1/modules/M16-05/verify", json=result)
    assert verified.status_code == 200
    assert verified.json() == result
    tampered = dict(result)
    tampered["result_digest"] = "sha256:" + "a" * 64
    assert client.post("/v1/modules/M16-05/verify", json=tampered).status_code == 422
    assert (
        client.post(
            "/v1/modules/M16-05/verify",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )


def test_fastapi_authorization_replay_and_inference_errors_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied = TestClient(app).post(
        "/v1/modules/M16-05/present",
        json=_request().model_dump(mode="json") | {"context": {"references": {}}},
    )
    assert denied.status_code == 403

    class ReplayService:
        def verify(self, _result: object, *, replay: bool = True) -> object:
            del replay
            raise M1605ReplayVerificationError

    monkeypatch.setattr(adapter_module, "_SERVICE", ReplayService())
    result = M1605Service().execute(_request()).model_dump(mode="json")
    assert TestClient(app).post("/v1/modules/M16-05/verify", json=result).status_code == 422

    class AuthorizationService:
        def _execute_validated(self, _request: object) -> object:
            raise M1605AuthorizationError

    monkeypatch.setattr(adapter_module, "_SERVICE", AuthorizationService())
    assert (
        TestClient(app)
        .post("/v1/modules/M16-05/present", json=_request().model_dump(mode="json"))
        .status_code
        == 403
    )

    class InferenceService:
        def _execute_validated(self, _request: object) -> object:
            raise M1605InferenceError

    monkeypatch.setattr(adapter_module, "_SERVICE", InferenceService())
    assert (
        TestClient(app)
        .post("/v1/modules/M16-05/present", json=_request().model_dump(mode="json"))
        .status_code
        == 422
    )


def test_typer_present_verify_export_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(m1605_app, ["export-schema", "request"]).exit_code == 0
    schema = runner.invoke(m1605_app, ["export-schema", "request"])
    assert json.loads(schema.stdout)["$schema"]
    assert runner.invoke(m1605_app, ["export-schema", "not-real"]).exit_code == 2
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    result_path = tmp_path / "result.json"
    assembled = runner.invoke(
        m1605_app, ["present", str(request_path), "--output", str(result_path)]
    )
    assert assembled.exit_code == 0
    assert result_path.exists()
    assert (
        runner.invoke(
            m1605_app, ["present", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1605_app, ["verify", str(result_path)]).exit_code == 0
    stdout_result = runner.invoke(m1605_app, ["present", str(request_path)])
    assert stdout_result.exit_code == 0
    assert "presented" in stdout_result.stdout
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert runner.invoke(m1605_app, ["present", str(invalid)]).exit_code != 0
    assert runner.invoke(m1605_app, ["verify", str(invalid)]).exit_code != 0


def test_plugin_strict_parse_once_and_forged_capability_rejection() -> None:
    plugin = M1605Plugin(M1605Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M16-05"
    token = plugin.validate(_request())
    assert plugin.run(token).status.value == "presented"
    assert isinstance(token, ValidatedM1605Request)
    forged = ValidatedM1605Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("ValidatedM1605Request", []))
    with pytest.raises(ValueError, match="duplicate"):
        plugin.validate('{"request_id":"a","request_id":"b"}')
    bytes_token = plugin.validate(canonical_json_bytes(_request()))
    assert plugin.run(bytes_token).status.value == "presented"
    assert plugin.verify(plugin.run(bytes_token)).status.value == "presented"

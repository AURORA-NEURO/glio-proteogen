"""FastAPI, Typer, and plugin parity tests for M17-06."""

# ruff: noqa: PLR2004

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.adapters.m1706 as adapter_module
from glio_proteogen.adapters.m1706 import app, m1706_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_06_reviewer_discrepancy_adjudication as m1706,
)
from tests.contract.test_m17_06_deep import _request

if TYPE_CHECKING:
    from pathlib import Path


def test_fastapi_schema_adjudicate_verify_and_strict_errors() -> None:
    client = TestClient(app)
    assert client.post("/v1/modules/M17-06/adjudicate", content=b"{}").status_code == 415
    assert client.get("/v1/m17-06/schema/request").status_code == 200
    assert client.get("/v1/m17-06/schema/not-real").status_code == 404
    assert (
        client.post(
            "/v1/modules/M17-06/adjudicate",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assembled = client.post(
        "/v1/modules/M17-06/adjudicate", json=_request().model_dump(mode="json")
    )
    assert assembled.status_code == 200
    result = assembled.json()
    verified = client.post("/v1/modules/M17-06/verify", json=result)
    assert verified.status_code == 200
    assert verified.json() == result
    tampered = dict(result)
    tampered["result_digest"] = "sha256:" + "a" * 64
    assert client.post("/v1/modules/M17-06/verify", json=tampered).status_code == 422
    assert (
        client.post(
            "/v1/modules/M17-06/verify",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )


def test_fastapi_authorization_and_export_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied = TestClient(app).post(
        "/v1/modules/M17-06/adjudicate",
        json=_request().model_dump(mode="json") | {"context": {"references": {}}},
    )
    assert denied.status_code == 403

    class FailingService:
        def _execute_validated(self, _request: object) -> object:
            raise m1706.M1706ExportError

    monkeypatch.setattr(adapter_module, "_SERVICE", FailingService())
    assert (
        TestClient(app)
        .post("/v1/modules/M17-06/adjudicate", json=_request().model_dump(mode="json"))
        .status_code
        == 422
    )


def test_typer_adjudicate_verify_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(m1706_app, ["export-schema", "request"]).exit_code == 0
    schema = runner.invoke(m1706_app, ["export-schema", "request"])
    assert json.loads(schema.stdout)["$schema"]
    assert runner.invoke(m1706_app, ["export-schema", "not-real"]).exit_code == 2
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    result_path = tmp_path / "result.json"
    assembled = runner.invoke(
        m1706_app, ["adjudicate", str(request_path), "--output", str(result_path)]
    )
    assert assembled.exit_code == 0
    assert result_path.exists()
    assert (
        runner.invoke(
            m1706_app, ["adjudicate", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1706_app, ["verify", str(result_path)]).exit_code == 0
    stdout_result = runner.invoke(m1706_app, ["adjudicate", str(request_path)])
    assert stdout_result.exit_code == 0
    assert "recorded" in stdout_result.stdout
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert runner.invoke(m1706_app, ["adjudicate", str(invalid)]).exit_code != 0
    assert runner.invoke(m1706_app, ["verify", str(invalid)]).exit_code != 0


def test_plugin_strict_parse_once_and_forged_token_rejection() -> None:
    plugin = m1706.M1706Plugin(m1706.M1706Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M17-06"
    token = plugin.validate(_request())
    assert plugin.run(token).status.value == "recorded"
    assert isinstance(token, m1706.ValidatedM1706Request)
    forged = m1706.ValidatedM1706Request(request=token.request, _seal=object())
    with pytest.raises(TypeError):
        plugin.run(forged)
    with_exception = plugin.validate(canonical_json_bytes(_request()))
    assert plugin.run(with_exception).status.value == "recorded"
    with pytest.raises(ValueError, match="duplicate"):
        plugin.validate('{"request_id":"a","request_id":"b"}')

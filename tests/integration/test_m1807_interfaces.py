"""FastAPI/Typer/plugin parity for M18-07."""

# ruff: noqa: PLR2004, TC002

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import glio_proteogen.adapters.m1807 as adapter_module
from glio_proteogen.adapters.m1807 import app, m1807_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c18_spatial_proteomics_projection import (
    m18_07_downstream_typed_export as m1807,
)
from tests.contract.test_m18_07_deep import _request

if TYPE_CHECKING:
    from pathlib import Path


def test_fastapi_export_verify_schema_and_sanitized_errors() -> None:
    client = TestClient(app)
    assert client.post("/v1/modules/M18-07/export", content=b"{}").status_code == 415
    assert client.get("/v1/m18-07/schema/request").status_code == 200
    assert client.get("/v1/m18-07/schema/not-real").status_code == 404
    assert (
        client.post(
            "/v1/modules/M18-07/export",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assembled = client.post("/v1/modules/M18-07/export", json=_request().model_dump(mode="json"))
    assert assembled.status_code == 200
    result = assembled.json()
    verified = client.post("/v1/modules/M18-07/verify", json=result)
    assert verified.status_code == 200
    assert verified.json() == result
    tampered = dict(result)
    tampered["result_digest"] = "sha256:" + "a" * 64
    assert client.post("/v1/modules/M18-07/verify", json=tampered).status_code == 422
    assert (
        client.post(
            "/v1/modules/M18-07/verify",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )


def test_fastapi_authorization_and_export_error_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied = TestClient(app).post(
        "/v1/modules/M18-07/export",
        json=_request().model_dump(mode="json") | {"context": {"references": {}}},
    )
    assert denied.status_code == 403

    class FailingService:
        def _execute_validated(self, _request: object) -> object:
            raise m1807.M1807ExportError

    monkeypatch.setattr(adapter_module, "_SERVICE", FailingService())
    assert (
        TestClient(app)
        .post("/v1/modules/M18-07/export", json=_request().model_dump(mode="json"))
        .status_code
        == 422
    )


def test_typer_export_verify_schema_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(m1807_app, ["export-schema", "request"]).exit_code == 0
    schema = runner.invoke(m1807_app, ["export-schema", "request"])
    assert json.loads(schema.stdout)["$schema"]
    assert runner.invoke(m1807_app, ["export-schema", "not-real"]).exit_code == 2
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    result_path = tmp_path / "result.json"
    assembled = runner.invoke(
        m1807_app, ["export", str(request_path), "--output", str(result_path)]
    )
    assert assembled.exit_code == 0
    assert result_path.exists()
    assert (
        runner.invoke(
            m1807_app, ["export", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1807_app, ["verify", str(result_path)]).exit_code == 0
    stdout_result = runner.invoke(m1807_app, ["export", str(request_path)])
    assert stdout_result.exit_code == 0
    assert "biomarker_panel_downstream_contract" in stdout_result.stdout
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert runner.invoke(m1807_app, ["export", str(invalid)]).exit_code != 0
    assert runner.invoke(m1807_app, ["verify", str(invalid)]).exit_code != 0

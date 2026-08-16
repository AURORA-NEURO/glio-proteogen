"""FastAPI, Typer and plugin parity tests for M18-04."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest  # noqa: TC002 - pytest is needed at runtime by parametrized fixtures.
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import m1804 as adapter
from glio_proteogen.adapters.m1804 import app, m1804_app
from glio_proteogen.modules.c18_spatial_proteomics_projection.m18_04_intended_use_adapter import (
    M1804Plugin,
)
from tests.contract.test_m18_04_deep import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNSUPPORTED_MEDIA = 415
_HTTP_UNPROCESSABLE = 422
_CLI_USAGE_ERROR = 2


def test_api_schema_resolution_and_content_type_boundary() -> None:
    with TestClient(app) as client:
        schema_response = client.get("/v1/m18-04/schema/request")
        assert schema_response.status_code == _HTTP_OK
        assert schema_response.json()["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M18-04"
        assert client.get("/v1/m18-04/schema/not-a-contract").status_code == _HTTP_NOT_FOUND
        assert (
            client.post("/v1/modules/M18-04/adapt", content=b"").status_code
            == _HTTP_UNSUPPORTED_MEDIA
        )


def test_api_adapt_verify_and_tamper_boundary() -> None:
    payload = _request().model_dump(mode="json")
    with TestClient(app) as client:
        adapted = client.post("/v1/modules/M18-04/adapt", json=payload)
        assert adapted.status_code == _HTTP_OK
        result = adapted.json()
        verified = client.post("/v1/modules/M18-04/verify", json=result)
        assert verified.status_code == _HTTP_OK
        tampered = dict(result)
        tampered["human_review_required"] = True
        assert (
            client.post("/v1/modules/M18-04/verify", json=tampered).status_code
            == _HTTP_UNPROCESSABLE
        )


def test_api_rejects_malformed_json_validation_and_service_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _request().model_dump(mode="json")
    invalid_payload = dict(payload)
    del invalid_payload["registration"]
    with TestClient(app) as client:
        assert (
            client.post(
                "/v1/modules/M18-04/adapt",
                content=b"{not-json",
                headers={"content-type": "application/json"},
            ).status_code
            == _HTTP_UNPROCESSABLE
        )
        assert (
            client.post("/v1/modules/M18-04/adapt", json=invalid_payload).status_code
            == _HTTP_UNPROCESSABLE
        )
        assert (
            client.post(
                "/v1/modules/M18-04/verify", content=b"{}", headers={"content-type": "text/plain"}
            ).status_code
            == _HTTP_UNSUPPORTED_MEDIA
        )
        assert (
            client.post(
                "/v1/modules/M18-04/verify",
                content=b"{not-json",
                headers={"content-type": "application/json"},
            ).status_code
            == _HTTP_UNPROCESSABLE
        )

        class FailingService:
            def adapt(self, _request: object) -> None:
                raise ValueError from None

        monkeypatch.setattr(adapter, "_SERVICE", FailingService())
        assert (
            client.post("/v1/modules/M18-04/adapt", json=payload).status_code == _HTTP_UNPROCESSABLE
        )


def test_cli_schema_adapt_no_overwrite_and_plugin_parity(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    output_path = tmp_path / "result.json"
    runner = CliRunner()
    schema = runner.invoke(m1804_app, ["export-schema", "output"])
    assert schema.exit_code == 0
    assert "GLIO-PROTEOGEN-M18-04" in schema.stdout
    adapted = runner.invoke(m1804_app, ["adapt", str(request_path), "--output", str(output_path)])
    assert adapted.exit_code == 0
    assert output_path.exists()
    no_overwrite = runner.invoke(
        m1804_app, ["adapt", str(request_path), "--output", str(output_path)]
    )
    assert no_overwrite.exit_code != 0
    result = json.loads(output_path.read_text(encoding="utf-8"))
    verified = runner.invoke(m1804_app, ["verify", str(output_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout) == result
    plugin = M1804Plugin()
    assert plugin.descriptor.owner == "Quality engineering"
    assert plugin.run(_request()).result_digest == result["result_digest"]


def test_cli_reports_unknown_schema_invalid_request_and_stdout(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m1804_app, ["export-schema", "unknown"])
    assert unknown.exit_code == _CLI_USAGE_ERROR
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{}", encoding="utf-8")
    invalid = runner.invoke(m1804_app, ["adapt", str(invalid_path)])
    assert invalid.exit_code == 1
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    stdout_result = runner.invoke(m1804_app, ["adapt", str(request_path)])
    assert stdout_result.exit_code == 0
    assert "result_digest" in stdout_result.stdout
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("{}", encoding="utf-8")
    failed_verify = runner.invoke(m1804_app, ["verify", str(bad_result)])
    assert failed_verify.exit_code == 1

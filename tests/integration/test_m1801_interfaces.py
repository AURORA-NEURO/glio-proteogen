"""FastAPI, Typer, and plugin parity tests for M18-01."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1801 import app, m1801_app
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m18_01_upstream_contract_resolver import (  # noqa: E501
    M1801Plugin,
)
from tests.modules.c17_metabolomic_lipidomic_integration.test_m18_01_engine import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNSUPPORTED_MEDIA = 415
_HTTP_UNPROCESSABLE = 422


def test_api_schema_resolution_and_sanitized_content_type_errors() -> None:
    with TestClient(app) as client:
        schema_response = client.get("/v1/m18-01/schema/request")
        assert schema_response.status_code == _HTTP_OK
        assert schema_response.json()["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M18-01"
        assert client.get("/v1/m18-01/schema/not-a-contract").status_code == _HTTP_NOT_FOUND
        assert (
            client.post("/v1/modules/M18-01/resolve", content=b"").status_code
            == _HTTP_UNSUPPORTED_MEDIA
        )


def test_api_resolve_verify_and_replay_error_boundary() -> None:
    payload = _request().model_dump(mode="json")
    with TestClient(app) as client:
        resolved = client.post("/v1/modules/M18-01/resolve", json=payload)
        assert resolved.status_code == _HTTP_OK
        result = resolved.json()
        verified = client.post("/v1/modules/M18-01/verify", json=result)
        assert verified.status_code == _HTTP_OK
        tampered = dict(result)
        tampered["human_review_required"] = True
        assert (
            client.post("/v1/modules/M18-01/verify", json=tampered).status_code
            == _HTTP_UNPROCESSABLE
        )


def test_cli_schema_resolution_no_overwrite_and_plugin_parity(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    output_path = tmp_path / "result.json"
    runner = CliRunner()
    schema = runner.invoke(m1801_app, ["export-schema", "output"])
    assert schema.exit_code == 0
    assert "GLIO-PROTEOGEN-M18-01" in schema.stdout
    resolved = runner.invoke(
        m1801_app, ["resolve", str(request_path), "--output", str(output_path)]
    )
    assert resolved.exit_code == 0
    assert output_path.exists()
    no_overwrite = runner.invoke(
        m1801_app, ["resolve", str(request_path), "--output", str(output_path)]
    )
    assert no_overwrite.exit_code != 0
    result = json.loads(output_path.read_text(encoding="utf-8"))
    verified = runner.invoke(m1801_app, ["verify", str(output_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout) == result
    plugin = M1801Plugin()
    assert plugin.descriptor.owner == "Computational biology"
    assert plugin.run(_request()).result_digest == result["result_digest"]

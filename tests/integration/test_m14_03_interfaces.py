"""HTTP and CLI parity tests for provisional M14-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app
from glio_proteogen.contracts.m14_03 import contract_json_schemas
from tests.modules.c14_microenvironment_protein_deconvolution.test_m14_03_runtime import (
    _request,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_HTTP_UNSUPPORTED_MEDIA = 415


def test_m1403_http_schema_and_execution_parity(tmp_path: Path) -> None:
    request = _request()
    with TestClient(create_app(tmp_path / "m1403.sqlite3")) as client:
        for name in contract_json_schemas():
            response = client.get(f"/v1/contracts/M14-03/{name}/schema")
            assert response.status_code == _HTTP_OK
            assert response.json()["$id"].endswith(f":{name}")
        response = client.post(
            "/v1/modules/M14-03/mechanistic-feature-construction",
            json=request.model_dump(mode="json"),
        )
        assert response.status_code == _HTTP_OK
        body = response.json()
        assert body["output_type"] == "protein_subtype_mechanistic_features"
        assert body["status"] == "constructed"
        bad_media = client.post(
            "/v1/modules/M14-03/mechanistic-feature-construction",
            content=request.model_dump_json(),
            headers={"content-type": "text/plain"},
        )
        assert bad_media.status_code == _HTTP_UNSUPPORTED_MEDIA


def test_m1403_http_denied_control_is_forbidden(tmp_path: Path) -> None:
    payload = _request().model_dump(mode="json")
    payload["context"]["references"]["quality"]["state"] = "rejected"
    with TestClient(create_app(tmp_path / "m1403-denied.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M14-03/mechanistic-feature-construction",
            json=payload,
        )
    assert response.status_code == _HTTP_FORBIDDEN


def test_m1403_cli_schema_and_construct_parity(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    schema = runner.invoke(app, ["mechanistic-features", "export-schema", "output"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M14-03"

    result = runner.invoke(app, ["mechanistic-features", "construct", str(request_path)])
    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["status"] == "constructed"

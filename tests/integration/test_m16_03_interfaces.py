"""HTTP and CLI parity checks for M16-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app
from glio_proteogen.contracts.m16_03 import M1603_DOSSIER_SLICE
from tests.runtime.test_m16_03_engine import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_HTTP_UNSUPPORTED_MEDIA = 415
_CONTRIBUTION_COUNT = 4


def test_http_schema_operation_and_authorization_boundary(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "m1603.sqlite")) as client:
        schema = client.get("/v1/contracts/M16-03/request/schema")
        assert schema.status_code == _HTTP_OK
        assert schema.json()["x-glio-contract"]["dossierSlice"] == M1603_DOSSIER_SLICE

        valid = client.post(
            "/v1/modules/M16-03/fusion-aggregation",
            json=_request().model_dump(mode="json"),
        )
        assert valid.status_code == _HTTP_OK
        assert valid.json()["status"] == "abstained"
        assert valid.json()["integrated_evidence"] is None

        denied_payload = _request().model_dump(mode="json")
        denied_payload["context"]["references"]["consent"]["state"] = "withheld"
        denied = client.post(
            "/v1/modules/M16-03/fusion-aggregation",
            json=denied_payload,
        )
        assert denied.status_code == _HTTP_FORBIDDEN

        wrong_media = client.post(
            "/v1/modules/M16-03/fusion-aggregation",
            content=json.dumps({}),
            headers={"content-type": "text/plain"},
        )
        assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA


def test_cli_schema_and_fusion(tmp_path: Path) -> None:
    runner = CliRunner()
    schema = runner.invoke(app, ["fusion-aggregation", "export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["dossierSlice"] == M1603_DOSSIER_SLICE

    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(_request().model_dump(mode="json")),
        encoding="utf-8",
    )
    fused = runner.invoke(app, ["fusion-aggregation", "fuse", str(request_path)])
    assert fused.exit_code == 0, fused.stdout
    assert json.loads(fused.stdout)["status"] == "abstained"

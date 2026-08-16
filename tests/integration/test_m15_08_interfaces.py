"""HTTP, CLI, and plugin parity checks for M15-08."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app
from glio_proteogen.contracts.m15_08 import M1508_DOSSIER_SLICE
from tests.runtime.test_m15_08_engine import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_HTTP_UNSUPPORTED_MEDIA = 415
_LINK_COUNT = 5


def test_http_schema_operation_and_authorization_boundary(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "m1508.sqlite")) as client:
        schema = client.get("/v1/contracts/M15-08/request/schema")
        assert schema.status_code == _HTTP_OK
        assert schema.json()["x-glio-contract"]["dossierSlice"] == M1508_DOSSIER_SLICE

        valid = client.post(
            "/v1/modules/M15-08/mechanism-evidence-dossier",
            json=_request().model_dump(mode="json"),
        )
        assert valid.status_code == _HTTP_OK
        assert valid.json()["status"] == "ready"
        assert len(valid.json()["dossier"]["links"]) == _LINK_COUNT

        denied_payload = _request().model_dump(mode="json")
        denied_payload["context"]["references"]["consent"]["state"] = "withheld"
        denied = client.post(
            "/v1/modules/M15-08/mechanism-evidence-dossier",
            json=denied_payload,
        )
        assert denied.status_code == _HTTP_FORBIDDEN

        wrong_media = client.post(
            "/v1/modules/M15-08/mechanism-evidence-dossier",
            content=json.dumps({}),
            headers={"content-type": "text/plain"},
        )
        assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA


def test_cli_schema_and_assembly(tmp_path: Path) -> None:
    runner = CliRunner()
    schema = runner.invoke(app, ["mechanism-dossier", "export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["dossierSlice"] == M1508_DOSSIER_SLICE

    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(_request().model_dump(mode="json")),
        encoding="utf-8",
    )
    assembled = runner.invoke(app, ["mechanism-dossier", "assemble", str(request_path)])
    assert assembled.exit_code == 0, assembled.stdout
    assert json.loads(assembled.stdout)["status"] == "ready"

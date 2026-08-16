"""HTTP, CLI, and plugin parity checks for M15-05."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app
from glio_proteogen.contracts.m15_05 import M1505_DOSSIER_SLICE
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_05_longitudinal_evolution as m1505,
)
from tests.runtime.test_m15_05_engine import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_UNSUPPORTED_MEDIA = 415


def test_http_schema_and_operation_enforce_strict_boundary(tmp_path: Path) -> None:
    database = tmp_path / "m1505.sqlite"
    with TestClient(create_app(database)) as client:
        schema_response = client.get("/v1/contracts/M15-05/request/schema")
        assert schema_response.status_code == _HTTP_OK
        assert schema_response.json()["x-glio-contract"]["dossierSlice"] == M1505_DOSSIER_SLICE

        valid_response = client.post(
            "/v1/modules/M15-05/longitudinal-evolution",
            json=_request().model_dump(mode="json"),
        )
        assert valid_response.status_code == _HTTP_OK
        assert valid_response.json()["status"] == "modeled"

        wrong_media = client.post(
            "/v1/modules/M15-05/longitudinal-evolution",
            content=json.dumps({}),
            headers={"content-type": "text/plain"},
        )
        assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA


def test_cli_schema_and_plugin_match_contract() -> None:
    runner = CliRunner()
    cli_result = runner.invoke(app, ["longitudinal-evolution", "export-schema", "request"])
    assert cli_result.exit_code == 0
    assert json.loads(cli_result.stdout)["x-glio-contract"]["dossierSlice"] == M1505_DOSSIER_SLICE

    plugin = m1505.M1505Plugin(m1505.M1505Service())
    validated = plugin.validate(_request())
    assert plugin.run(validated).status.value == "modeled"

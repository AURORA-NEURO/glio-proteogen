"""API and CLI parity tests for M05-07."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m05_07 import PtmLocalizationSupportRouteResult
from tests.contract.test_m05_07_hardening import _request

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

_SCHEMA_NAMES: Final = ("request", "output", "policy", "prerequisites", "fact", "receipt")
_HTTP_OK: Final = 200
_HTTP_FORBIDDEN: Final = 403
_CLI_USAGE_ERROR: Final = 2


@pytest.mark.parametrize("name", _SCHEMA_NAMES)
def test_api_and_cli_export_same_m05_07_schema(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M05-07/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["ptm-localization-support", "export-schema", name])

    assert response.status_code == _HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)


def test_api_and_cli_emit_same_m05_07_route(tmp_path: Path) -> None:
    request = _request()
    payload = request.model_dump_json()
    request_path = tmp_path / "support-request.json"
    request_path.write_text(payload, encoding="utf-8")

    with TestClient(create_app(tmp_path / "route.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M05-07/support-route",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["ptm-localization-support", "route", str(request_path)],
    )

    assert response.status_code == _HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert PtmLocalizationSupportRouteResult.model_validate_json(
        response.content, strict=True
    ) == PtmLocalizationSupportRouteResult.model_validate_json(cli.stdout, strict=True)


def test_api_denied_control_returns_forbidden(tmp_path: Path) -> None:
    payload = _request().model_dump(mode="json")
    payload["context"]["references"]["quality"]["state"] = "rejected"

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M05-07/support-route",
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == _HTTP_FORBIDDEN


def test_cli_invalid_request_is_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text('{"operation":"route_ptm_localization_support"}', encoding="utf-8")

    cli = CliRunner().invoke(cli_app, ["ptm-localization-support", "route", str(path)])

    assert cli.exit_code == _CLI_USAGE_ERROR
    assert "invalid" in cli.output.lower()
    assert "Traceback" not in cli.output

"""Black-box checks for the thin stateless M01-07 transports."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m01_07.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m01_07 import SupportRoutingResult

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES = (
    "request",
    "output",
    "policy",
    "profile",
    "criterion",
    "evidence",
    "assessment",
)
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_the_same_schema(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M01-07/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["support", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)


def test_api_and_cli_emit_the_same_support_route(tmp_path: Path) -> None:
    request = build_scenario_request("supported")
    payload = request.model_dump_json()
    request_path = tmp_path / "support-request.json"
    request_path.write_text(payload, encoding="utf-8")

    with TestClient(create_app(tmp_path / "support.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-07/route",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["support", "route", str(request_path)])

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = SupportRoutingResult.model_validate_json(response.content, strict=True)
    cli_result = SupportRoutingResult.model_validate_json(cli.stdout, strict=True)
    assert api_result == cli_result
    assert api_result.decision.value == "supported"


def test_denied_consent_is_rejected_before_typed_processing(tmp_path: Path) -> None:
    payload = build_scenario_request("consent_denied").model_dump(mode="json")
    payload["context"]["references"]["consent"]["state"] = "withheld"

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-07/route",
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == HTTP_FORBIDDEN


def test_duplicate_json_and_invalid_cli_request_fail_safely(tmp_path: Path) -> None:
    duplicate = '{"operation":"route_support","operation":"route_support"}'
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text('{"operation":"route_support"}', encoding="utf-8")

    with TestClient(create_app(tmp_path / "invalid.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-07/route",
            content=duplicate,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["support", "route", str(invalid_path)])

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "invalid request" in cli.output
    assert "Traceback" not in cli.output

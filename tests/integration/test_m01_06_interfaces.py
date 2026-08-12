"""Black-box checks for the thin stateless M01-06 transports."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m01_06.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m01_06 import HarmonizationResult

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES = (
    "request",
    "output",
    "policy",
    "profile",
    "invariant",
    "value",
    "transformation",
)
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_the_same_schema(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M01-06/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["harmonize", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)


def test_api_and_cli_emit_the_same_harmonization(tmp_path: Path) -> None:
    request = build_scenario_request("supported")
    payload = request.model_dump_json()
    request_path = tmp_path / "harmonization-request.json"
    request_path.write_text(payload, encoding="utf-8")

    with TestClient(create_app(tmp_path / "harmonization.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-06/harmonize",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["harmonize", "run", str(request_path)])

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = HarmonizationResult.model_validate_json(response.content, strict=True)
    cli_result = HarmonizationResult.model_validate_json(cli.stdout, strict=True)
    assert api_result == cli_result
    assert api_result.disposition.value == "accepted"


def test_denied_consent_is_rejected_before_typed_processing(tmp_path: Path) -> None:
    request = build_scenario_request("consent_denied")
    payload = request.model_dump(mode="json")
    payload["context"]["references"]["consent"]["state"] = "withheld"

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-06/harmonize",
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == HTTP_FORBIDDEN


def test_duplicate_json_and_invalid_cli_request_fail_safely(tmp_path: Path) -> None:
    duplicate = (
        '{"operation":"harmonize_observations",'
        '"operation":"harmonize_observations"}'
    )
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text('{"operation":"harmonize_observations"}', encoding="utf-8")

    with TestClient(create_app(tmp_path / "invalid.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-06/harmonize",
            content=duplicate,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["harmonize", "run", str(invalid_path)])

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "invalid request" in cli.output
    assert "Traceback" not in cli.output

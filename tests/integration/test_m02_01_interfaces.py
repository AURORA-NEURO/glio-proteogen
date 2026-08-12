"""Black-box checks for the thin stateless M02-01 transports."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m02_01.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m02_01 import ConformanceEvaluation

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES = ("request", "output", "schema", "profile", "observation")
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_the_same_schema(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M02-01/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["identification", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)


def test_api_and_cli_emit_the_same_conformance_result(tmp_path: Path) -> None:
    request = build_scenario_request("canonical")
    payload = request.model_dump_json()
    request_path = tmp_path / "metadata-request.json"
    request_path.write_text(payload, encoding="utf-8")

    with TestClient(create_app(tmp_path / "metadata.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M02-01/conformance",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["identification", "validate-metadata", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = ConformanceEvaluation.model_validate_json(response.content, strict=True)
    cli_result = ConformanceEvaluation.model_validate_json(cli.stdout, strict=True)
    assert api_result == cli_result
    assert api_result.disposition.value == "conformant"


def test_denied_consent_is_rejected_by_api_preflight(tmp_path: Path) -> None:
    payload = build_scenario_request("consent_denied").model_dump(mode="json")
    payload["context"]["references"]["consent"]["state"] = "withheld"

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M02-01/conformance",
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == HTTP_FORBIDDEN

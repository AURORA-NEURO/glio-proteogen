"""Black-box parity checks for the thin M02-02 transports."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m02_02.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m02_02 import IdentityBindingEvaluation

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
SCHEMAS = ("request", "output", "policy", "binding", "finding")


@pytest.mark.parametrize("name", SCHEMAS)
def test_api_and_cli_export_identical_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M02-02/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["binding", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)


def test_api_and_cli_emit_identical_audit_results(tmp_path: Path) -> None:
    request = build_scenario_request("canonical")
    payload = request.model_dump_json()
    request_path = tmp_path / "binding-request.json"
    request_path.write_text(payload, encoding="utf-8")

    with TestClient(create_app(tmp_path / "binding.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M02-02/audit-bindings",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["binding", "audit", str(request_path)])

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = IdentityBindingEvaluation.model_validate_json(response.content, strict=True)
    cli_result = IdentityBindingEvaluation.model_validate_json(cli.stdout, strict=True)
    assert api_result == cli_result
    assert api_result.disposition.value == "conformant"


def test_api_rejects_denied_consent_in_raw_preflight(tmp_path: Path) -> None:
    payload = build_scenario_request("canonical").model_dump(mode="json")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["bindings"] = {"must_not": "be traversed as bindings"}

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M02-02/audit-bindings",
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == HTTP_FORBIDDEN

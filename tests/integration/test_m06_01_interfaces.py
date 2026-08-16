"""Black-box Python, HTTP, and CLI parity checks for M06-01."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m06_01 import (
    ValidateFormalProteinStateResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema import (
    M0601Plugin,
    M0601Service,
    validate_formal_protein_state,
)
from tests.contract.test_m06_01_hardening import _request

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "schema",
    "feature-definition",
    "feature-value",
    "invariant",
    "invariant-result",
    "migration",
)
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m0601_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M06-01/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["formal-state", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]


def test_python_http_and_cli_emit_exact_result_parity(tmp_path: Path) -> None:
    request = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "formal-state-request.json"
    request_path.write_bytes(serialized)
    plugin = M0601Plugin(M0601Service())

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M06-01/formal-state-validation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["formal-state", "validate", str(request_path)])

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = ValidateFormalProteinStateResult.model_validate_json(response.content)
    cli_result = ValidateFormalProteinStateResult.model_validate_json(cli.stdout)
    expected = validate_formal_protein_state(request)
    assert expected == M0601Service().execute(request)
    assert expected == plugin.run(plugin.validate(request)) == api_result == cli_result


def test_api_and_cli_reject_denied_control_before_schema_execution(tmp_path: Path) -> None:
    payload = _request().model_dump(mode="json")
    payload["context"]["references"]["quality"]["state"] = "rejected"
    payload["state_schema"] = "must_not_be_traversed"
    serialized = json.dumps(payload)
    request_path = tmp_path / "denied.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M06-01/formal-state-validation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["formal-state", "validate", str(request_path)])

    assert response.status_code == HTTP_FORBIDDEN
    assert "accepted upstream controls" in response.json()["detail"]
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "must_not_be_traversed" not in cli.output
    assert "Traceback" not in cli.output


def test_api_rejects_wrong_media_type_and_malformed_json(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "invalid.sqlite3")) as client:
        media_type = client.post(
            "/v1/modules/M06-01/formal-state-validation",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        malformed = client.post(
            "/v1/modules/M06-01/formal-state-validation",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )

    assert media_type.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert malformed.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_cli_rejects_unknown_request_field_without_reflection(tmp_path: Path) -> None:
    payload = _request().model_dump(mode="json")
    payload["unexpected"] = "field-canary"
    request_path = tmp_path / "unknown.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")

    cli = CliRunner().invoke(cli_app, ["formal-state", "validate", str(request_path)])

    assert cli.exit_code == CLI_USAGE_ERROR
    assert "field-canary" not in cli.output
    assert "Traceback" not in cli.output

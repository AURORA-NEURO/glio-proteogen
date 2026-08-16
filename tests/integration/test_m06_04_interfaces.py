"""Python, HTTP, CLI, and plugin parity for provisional M06-04."""

from __future__ import annotations

import json
from typing import Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m06_04 import (
    EstimateProteinAbundanceProbabilisticResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c06_protein_abundance.m06_04_probabilistic_advanced_estimator import (
    M0604Plugin,
    M0604Service,
)
from tests.contract.test_m06_04_hardening import _request

pytestmark = pytest.mark.integration

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "configuration",
    "prior",
    "constraint",
    "posterior",
    "diagnostic",
)
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m0604_schemas(tmp_path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M06-04/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["probabilistic-estimator", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]


def test_python_http_cli_and_plugin_emit_exact_result_parity(tmp_path) -> None:
    request = _request()
    serialized = canonical_json_bytes(request)
    request_path = tmp_path / "m0604-request.json"
    request_path.write_bytes(serialized)
    plugin = M0604Plugin(M0604Service())

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M06-04/probabilistic-estimation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["probabilistic-estimator", "estimate", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = EstimateProteinAbundanceProbabilisticResult.model_validate_json(response.content)
    cli_result = EstimateProteinAbundanceProbabilisticResult.model_validate_json(cli.stdout)
    expected = M0604Service().estimate(request)
    plugin_result = plugin.run(plugin.validate(request))
    assert expected == plugin_result == api_result == cli_result


def test_api_and_cli_reject_denied_control_before_schema_execution(tmp_path) -> None:
    payload = json.loads(canonical_json_bytes(_request()).decode("utf-8"))
    payload["context"]["references"]["quality"]["state"] = "rejected"
    payload["state_schema"] = "must_not_be_traversed"
    serialized = json.dumps(payload)
    request_path = tmp_path / "denied.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M06-04/probabilistic-estimation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["probabilistic-estimator", "estimate", str(request_path)],
    )

    assert response.status_code == HTTP_FORBIDDEN
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "must_not_be_traversed" not in cli.output
    assert "Traceback" not in cli.output


def test_api_rejects_wrong_media_type_and_malformed_json(tmp_path) -> None:
    with TestClient(create_app(tmp_path / "invalid.sqlite3")) as client:
        media_type = client.post(
            "/v1/modules/M06-04/probabilistic-estimation",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        malformed = client.post(
            "/v1/modules/M06-04/probabilistic-estimation",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )

    assert media_type.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert malformed.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_cli_rejects_unknown_request_field_without_reflection(tmp_path) -> None:
    payload = json.loads(canonical_json_bytes(_request()).decode("utf-8"))
    payload["unexpected"] = "field-canary"
    request_path = tmp_path / "unknown.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")

    cli = CliRunner().invoke(
        cli_app,
        ["probabilistic-estimator", "estimate", str(request_path)],
    )

    assert cli.exit_code == CLI_USAGE_ERROR
    assert "field-canary" not in cli.output
    assert "Traceback" not in cli.output

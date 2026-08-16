"""Black-box API, CLI, and schema parity checks for M14-05."""

from __future__ import annotations

import json
from typing import Final

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m14_05 import (
    ModelProteinSubtypeLongitudinalEvolutionRequest,
    ProteinSubtypeLongitudinalEvolutionResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution import (
    m14_05_protein_subtype_evolution as m1405,
)
from tests.modules.c14_microenvironment_protein_deconvolution.test_m14_05_runtime import (
    _request,
)

pytestmark = pytest.mark.integration

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "observation",
    "trajectory-state",
    "change-point",
    "configuration",
    "policy",
    "diagnostic",
)
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_UNSUPPORTED_MEDIA: Final = 415


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_library_api_and_cli_export_identical_schemas(tmp_path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M14-05/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["longitudinal-evolution", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]


def test_library_plugin_api_and_cli_emit_exact_result_parity(tmp_path) -> None:
    request = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(serialized)
    plugin = m1405.M1405Plugin(m1405.M1405Service())
    token = plugin.validate(serialized)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M14-05/longitudinal-evolution",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["longitudinal-evolution", "infer", str(request_path)])

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteinSubtypeLongitudinalEvolutionResult.model_validate_json(
        response.content, strict=True
    )
    cli_result = ProteinSubtypeLongitudinalEvolutionResult.model_validate_json(
        cli.stdout, strict=True
    )
    expected = m1405.M1405Service().execute(request)
    assert expected == plugin.run(token) == api_result == cli_result


def test_api_rejects_non_json_and_denied_controls_before_execution(tmp_path) -> None:
    request = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    with TestClient(create_app(tmp_path / "errors.sqlite3")) as client:
        media_response = client.post(
            "/v1/modules/M14-05/longitudinal-evolution",
            content=serialized,
            headers={"content-type": "text/plain"},
        )
        payload = request.model_dump(mode="json")
        payload["context"]["references"]["consent"]["state"] = "withheld"
        denied_response = client.post(
            "/v1/modules/M14-05/longitudinal-evolution",
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )

    assert media_response.status_code == HTTP_UNSUPPORTED_MEDIA
    assert denied_response.status_code == HTTP_FORBIDDEN


def test_strict_model_boundary_rejects_unknown_field() -> None:
    payload = _request().model_dump(mode="json")
    payload["unexpected"] = "reject"
    with pytest.raises(ValidationError, match="extra"):
        ModelProteinSubtypeLongitudinalEvolutionRequest.model_validate(payload, strict=True)

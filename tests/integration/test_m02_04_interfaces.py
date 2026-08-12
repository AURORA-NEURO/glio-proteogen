"""Black-box checks for M02-04 schema, API, and CLI parity."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m02_04.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m02_04 import (
    IdentificationQualityProfile,
)
from glio_proteogen.modules.c02_identification_qc.m02_04_quality_metrics import (
    M0204Service,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
SCHEMAS = (
    "request",
    "output",
    "assay_profile",
    "policy",
    "threshold",
    "observation",
    "metric",
)


@pytest.mark.parametrize("name", SCHEMAS)
def test_api_and_cli_export_identical_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M02-04/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["identification-quality", "export-schema", name],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["x-glio-contract"]["biologicalInterpretation"] is False


def test_api_cli_and_service_compute_identical_profiles(tmp_path: Path) -> None:
    request = build_scenario_request()
    expected = M0204Service().execute(request)
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M02-04/quality",
            content=request.model_dump_json(),
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["identification-quality", "compute", str(request_path)],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert (
        IdentificationQualityProfile.model_validate_json(response.content, strict=True)
        == expected
    )
    assert IdentificationQualityProfile.model_validate_json(cli.stdout, strict=True) == expected


def test_api_denied_consent_precedes_typed_observation_validation(
    tmp_path: Path,
) -> None:
    request = build_scenario_request().model_dump(mode="json")
    request["context"]["references"]["consent"]["state"] = "withheld"
    sentinel = "PRIVATE_OBSERVATION_CANARY"
    request["observations"] = [{"metric_code": sentinel}]

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post("/v1/modules/M02-04/quality", json=request)

    assert response.status_code == HTTP_FORBIDDEN
    assert sentinel not in response.text

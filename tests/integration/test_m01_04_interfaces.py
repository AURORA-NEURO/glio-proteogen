"""Black-box checks for the thin stateless M01-04 transport surfaces."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from evals.m01_04.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m01_04 import QualityProfile

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES = (
    "request",
    "output",
    "policy",
    "assay_profile",
    "metric_definition",
    "observation",
    "quality_metric",
)
HTTP_OK = 200


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_the_same_schema(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M01-04/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["quality", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)


def test_api_and_cli_compute_the_same_quality_profile(tmp_path: Path) -> None:
    request = build_scenario_request("complete")
    payload = request.model_dump_json()
    request_path = tmp_path / "quality-request.json"
    request_path.write_text(payload, encoding="utf-8")

    with TestClient(create_app(tmp_path / "quality.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-04/quality",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["quality", "compute", str(request_path)])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    api_profile = QualityProfile.model_validate_json(response.content, strict=True)
    cli_profile = QualityProfile.model_validate_json(cli.stdout, strict=True)
    assert api_profile == cli_profile
    assert api_profile.disposition.value == "accepted"

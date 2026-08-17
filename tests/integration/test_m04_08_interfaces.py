"""FastAPI/Typer parity for the M04-08 schema boundary."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "policy",
    "artifact",
    "manifest",
    "verification",
    "signature",
    "stage-provenance",
    "reproduction-evidence",
)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m04_08_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M04-08/{name}/schema")

    cli = CliRunner().invoke(cli_app, ["proteoform-release", "export-schema", name])

    assert response.status_code == 200
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$id"] == (
        f"urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-08:1.0.0:{name}"
    )
    assert response.json()["x-glio-contract"]["biologicalInterpretation"] is False


def test_m04_08_schema_boundaries_reject_unknown_contracts(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "invalid.sqlite3")) as client:
        response = client.get("/v1/contracts/M04-08/not-a-contract/schema")

    cli = CliRunner().invoke(cli_app, ["proteoform-release", "export-schema", "not-a-contract"])

    assert response.status_code == 422
    assert cli.exit_code != 0
    assert "Traceback" not in cli.output

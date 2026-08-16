"""M13-06 API/CLI parity and transport checks."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m13_06 import contract_json_schema
from glio_proteogen.contracts.m13_06.v1 import ProteotypePerturbationSensitivityResult
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c13_proteotype.m13_06_perturbation_sensitivity import (
    M1306Service,
)
from tests.modules.c13_proteotype.test_m13_06_runtime import _request

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
SCHEMA_NAMES: Final = (
    "request",
    "output",
    "scenario",
    "response",
    "sensitivity-surface",
    "configuration",
    "policy",
    "finding",
)
HTTP_OK: Final = 200
HTTP_UNSUPPORTED_MEDIA: Final = 415


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m1306_schema(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M13-06/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["proteotype-sensitivity", "export-schema", name])
    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]


def test_api_matches_service_and_strict_content_type(tmp_path: Path) -> None:
    request = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M13-06/perturbations",
            content=serialized,
            headers={"content-type": "application/json"},
        )
        wrong_type = client.post(
            "/v1/modules/M13-06/perturbations",
            content=serialized,
            headers={"content-type": "text/plain"},
        )
    assert response.status_code == HTTP_OK, response.text
    assert wrong_type.status_code == HTTP_UNSUPPORTED_MEDIA
    api_result = ProteotypePerturbationSensitivityResult.model_validate_json(
        response.content, strict=True
    )
    assert api_result == M1306Service().execute(request)

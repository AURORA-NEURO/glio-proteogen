"""Black-box checks for the thin stateless M01-05 transport surfaces."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m01_05.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m01_05 import ArtifactDetectionResult

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES = ("request", "output", "policy", "profile", "rule", "signal", "flag")
HTTP_OK: Final = 200
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_the_same_schema(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M01-05/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["artifact", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)


def test_api_and_cli_emit_the_same_detection_result(tmp_path: Path) -> None:
    request = build_scenario_request("clean")
    payload = request.model_dump_json()
    request_path = tmp_path / "artifact-request.json"
    request_path.write_text(payload, encoding="utf-8")

    with TestClient(create_app(tmp_path / "artifact.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M01-05/detect",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["artifact", "detect", str(request_path)])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    api_result = ArtifactDetectionResult.model_validate_json(response.content, strict=True)
    cli_result = ArtifactDetectionResult.model_validate_json(cli.stdout, strict=True)
    assert api_result == cli_result
    assert api_result.disposition.value == "accepted"


def test_api_requires_json_and_rejects_duplicate_keys(tmp_path: Path) -> None:
    request = build_scenario_request("clean")
    payload = request.model_dump_json()
    duplicate = '{"operation":"detect_artifacts","operation":"detect_artifacts"}'

    with TestClient(create_app(tmp_path / "invalid.sqlite3")) as client:
        media = client.post(
            "/v1/modules/M01-05/detect",
            content=payload,
            headers={"content-type": "text/plain"},
        )
        malformed = client.post(
            "/v1/modules/M01-05/detect",
            content=duplicate,
            headers={"content-type": "application/json"},
        )

    assert media.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert malformed.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_cli_rejects_invalid_request_without_traceback(tmp_path: Path) -> None:
    request_path = tmp_path / "invalid.json"
    request_path.write_text('{"operation":"detect_artifacts"}', encoding="utf-8")

    result = CliRunner().invoke(cli_app, ["artifact", "detect", str(request_path)])

    assert result.exit_code == CLI_USAGE_ERROR
    assert "invalid request" in result.output
    assert "Traceback" not in result.output

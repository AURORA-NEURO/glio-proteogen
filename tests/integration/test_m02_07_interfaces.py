"""Black-box checks for M02-07 joint support-routing interfaces."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m02_07.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m02_07 import IdentificationSupportRouteResult
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router import M0207Service

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2
SCHEMAS = (
    "request",
    "output",
    "prerequisites",
    "profile",
    "policy",
    "declaration",
    "envelope",
    "abstention",
)


@pytest.mark.parametrize("name", SCHEMAS)
def test_api_and_cli_export_identical_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M02-07/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["identification-support", "export-schema", name],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["x-glio-contract"]["jointEnvelopeRequired"] is True


def test_api_cli_and_service_emit_identical_results(tmp_path: Path) -> None:
    request = build_scenario_request()
    expected = M0207Service().execute(request)
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M02-07/support-route",
            content=request.model_dump_json(),
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["identification-support", "route", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert (
        IdentificationSupportRouteResult.model_validate_json(
            response.content,
            strict=True,
        )
        == expected
    )
    assert (
        IdentificationSupportRouteResult.model_validate_json(
            cli.stdout,
            strict=True,
        )
        == expected
    )


def test_denied_consent_precedes_hostile_receipt_traversal(tmp_path: Path) -> None:
    request = build_scenario_request().model_dump(mode="json")
    request["context"]["references"]["consent"]["state"] = "withheld"
    sentinel = "PRIVATE_M0207_CANARY"
    request["prerequisites"] = {"hostile": sentinel}
    request_path = tmp_path / "denied.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post("/v1/modules/M02-07/support-route", json=request)
    cli = CliRunner().invoke(
        cli_app,
        ["identification-support", "route", str(request_path)],
    )

    assert response.status_code == HTTP_FORBIDDEN
    assert sentinel not in response.text
    assert cli.exit_code == CLI_USAGE_ERROR
    assert sentinel not in cli.output
    assert "Traceback" not in cli.output


def test_api_and_cli_enforce_strict_json_boundaries(tmp_path: Path) -> None:
    payload = build_scenario_request().model_dump_json()
    duplicate = (
        '{"operation":"route_identification_support","operation":"route_identification_support"}'
    )
    request_path = tmp_path / "duplicate.json"
    request_path.write_text(duplicate, encoding="utf-8")

    with TestClient(create_app(tmp_path / "strict.sqlite3")) as client:
        media = client.post(
            "/v1/modules/M02-07/support-route",
            content=payload,
            headers={"content-type": "text/plain"},
        )
        malformed = client.post(
            "/v1/modules/M02-07/support-route",
            content=duplicate,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["identification-support", "route", str(request_path)],
    )

    assert media.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert malformed.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "duplicate" in cli.output.lower()
    assert "Traceback" not in cli.output

"""HTTP, CLI, and plugin parity checks for M15-05."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app
from glio_proteogen.contracts.m15_05 import M1505_DOSSIER_SLICE
from glio_proteogen.modules.c15_longitudinal_recurrence_proteotype import (
    m15_05_longitudinal_evolution as m1505,
)
from tests.runtime.test_m15_05_engine import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_UNSUPPORTED_MEDIA = 415


def test_http_schema_and_operation_enforce_strict_boundary(tmp_path: Path) -> None:
    database = tmp_path / "m1505.sqlite"
    with TestClient(create_app(database)) as client:
        schema_response = client.get("/v1/contracts/M15-05/request/schema")
        assert schema_response.status_code == _HTTP_OK
        assert schema_response.json()["x-glio-contract"]["dossierSlice"] == M1505_DOSSIER_SLICE

        valid_response = client.post(
            "/v1/modules/M15-05/longitudinal-evolution",
            json=_request().model_dump(mode="json"),
        )
        assert valid_response.status_code == _HTTP_OK
        assert valid_response.json()["status"] == "modeled"

        wrong_media = client.post(
            "/v1/modules/M15-05/longitudinal-evolution",
            content=json.dumps({}),
            headers={"content-type": "text/plain"},
        )
        assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA


def test_standalone_http_api_sanitizes_schema_and_json_boundaries() -> None:
    with TestClient(m1505.api.create_app()) as client:
        unknown_schema = client.get("/v1/contracts/M15-05/unknown/schema")
        wrong_media = client.post(
            "/v1/modules/M15-05/longitudinal-evolution",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        malformed = client.post(
            "/v1/modules/M15-05/longitudinal-evolution",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
    assert unknown_schema.status_code == HTTPStatus.NOT_FOUND
    assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_standalone_http_api_sanitizes_service_failures() -> None:
    class AuthorizationFailure(m1505.M1505Service):
        def execute(self, _payload: object) -> object:
            raise m1505.M1505AuthorizationError

    class ValidationFailure(m1505.M1505Service):
        def execute(self, _payload: object) -> object:
            raise ValueError from None

    body = _request().model_dump(mode="json")
    denied = TestClient(m1505.api.create_app(AuthorizationFailure())).post(
        "/v1/modules/M15-05/longitudinal-evolution", json=body
    )
    invalid = TestClient(m1505.api.create_app(ValidationFailure())).post(
        "/v1/modules/M15-05/longitudinal-evolution", json=body
    )
    assert denied.status_code == HTTPStatus.FORBIDDEN
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "internal detail" not in invalid.text


def test_cli_schema_and_plugin_match_contract() -> None:
    runner = CliRunner()
    cli_result = runner.invoke(
        app, ["m15-05-longitudinal-evolution", "export-schema", "request"]
    )
    assert cli_result.exit_code == 0
    assert json.loads(cli_result.stdout)["x-glio-contract"]["dossierSlice"] == M1505_DOSSIER_SLICE

    plugin = m1505.M1505Plugin(m1505.M1505Service())
    validated = plugin.validate(_request())
    assert plugin.run(validated).status.value == "modeled"

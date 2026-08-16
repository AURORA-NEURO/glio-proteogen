"""FastAPI, Typer, and strict interface parity for M23-04."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material.m23_04_external_transport_evaluator import (
    M2304Service,
    cli_app,
    create_app,
)
from tests.contract.test_m2304_deep import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - dependency is an optional interface extra.
    TestClient = None  # type: ignore[assignment,misc]


def test_cli_exports_all_contract_schema(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "request.json"
    result = runner.invoke(cli_app, ["export-schema", "request", "--output", str(target)])
    assert result.exit_code == 0
    assert json.loads(target.read_text()) ["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M23-04"


def test_cli_refuses_schema_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "schema.json"
    target.write_text("preserve")
    result = runner.invoke(cli_app, ["export-schema", "request", "--output", str(target)])
    assert result.exit_code != 0
    assert target.read_text() == "preserve"


def test_cli_validate_and_evaluate_round_trip(tmp_path: Path) -> None:
    runner = CliRunner()
    source = tmp_path / "request.json"
    output = tmp_path / "result.json"
    source.write_text(_request().model_dump_json())
    validated = runner.invoke(cli_app, ["validate", str(source)])
    evaluated = runner.invoke(cli_app, ["evaluate", str(source), "--output", str(output)])
    assert validated.exit_code == 0
    assert evaluated.exit_code == 0
    assert json.loads(output.read_text())["status"] == "evaluated"


def test_cli_verify_replays_result(tmp_path: Path) -> None:
    runner = CliRunner()
    source = tmp_path / "request.json"
    output = tmp_path / "result.json"
    source.write_text(_request().model_dump_json())
    assert runner.invoke(cli_app, ["evaluate", str(source), "--output", str(output)]).exit_code == 0
    verified = runner.invoke(cli_app, ["verify", str(output)])
    assert verified.exit_code == 0
    assert '"verified": true' in verified.stdout


def test_cli_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    runner = CliRunner()
    source = tmp_path / "request.json"
    source.write_text('{"request_id":"a","request_id":"b"}')
    result = runner.invoke(cli_app, ["validate", str(source)])
    assert result.exit_code != 0
    assert "input must satisfy" in result.output


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client is unavailable")
def test_api_exposes_schema_and_strict_validation() -> None:
    assert TestClient is not None
    client = TestClient(create_app())
    schema = client.get("/v1/modules/M23-04/schemas/request")
    assert schema.status_code == _HTTP_OK
    assert schema.json()["x-glio-contract"]["dossierSlice"].endswith("8088-8128")
    response = client.post("/v1/modules/M23-04/validate", json=_request().model_dump(mode="json"))
    assert response.status_code == _HTTP_OK


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client is unavailable")
def test_api_evaluate_and_verify_parity() -> None:
    assert TestClient is not None
    client = TestClient(create_app(M2304Service()))
    evaluated = client.post("/v1/modules/M23-04/evaluate", json=_request().model_dump(mode="json"))
    assert evaluated.status_code == _HTTP_OK
    result = evaluated.json()
    verified = client.post("/v1/modules/M23-04/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True


@pytest.mark.skipif(TestClient is None, reason="FastAPI test client is unavailable")
def test_api_sanitizes_malformed_request() -> None:
    assert TestClient is not None
    client = TestClient(create_app())
    response = client.post("/v1/modules/M23-04/evaluate", content=b'{"x":1,"x":2}')
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text

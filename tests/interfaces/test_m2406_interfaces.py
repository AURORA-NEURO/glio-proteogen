"""FastAPI, Typer, and strict plugin interface parity for M24-06."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from evals.m24_06.fixture import build_request, denied_request, unsupported_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material.m24_06_robustness_shift_ood_challenge import (
    M2406Service,
    cli_app,
    create_app,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422
_HTTP_NOT_FOUND = 404
_SCHEMA_COUNT = 8


def test_fastapi_schema_validate_challenge_and_verify_parity() -> None:
    client = TestClient(create_app(M2406Service()))
    schemas = client.get("/v1/modules/M24-06/schemas")
    assert schemas.status_code == _HTTP_OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    request_json = build_request().model_dump_json()
    validated = client.post("/v1/modules/M24-06/validate", content=request_json)
    assert validated.status_code == _HTTP_OK
    challenged = client.post("/v1/modules/M24-06/challenge", content=request_json)
    assert challenged.status_code == _HTTP_OK
    result = challenged.json()
    verified = client.post("/v1/modules/M24-06/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True


def test_fastapi_sanitizes_malformed_denied_and_unknown_requests() -> None:
    client = TestClient(create_app(M2406Service()))
    assert (
        client.post("/v1/modules/M24-06/validate", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    assert (
        client.post("/v1/modules/M24-06/verify", content=b"not-json").status_code
        == _HTTP_UNPROCESSABLE
    )
    denied = client.post("/v1/modules/M24-06/challenge", content=denied_request().model_dump_json())
    assert denied.status_code == _HTTP_UNPROCESSABLE
    unknown = client.get("/v1/modules/M24-06/schemas/not-a-contract")
    assert unknown.status_code == _HTTP_NOT_FOUND
    assert "Traceback" not in denied.text


def test_fastapi_abstention_preserves_safe_failure() -> None:
    client = TestClient(create_app(M2406Service()))
    response = client.post(
        "/v1/modules/M24-06/challenge", content=unsupported_request().model_dump_json()
    )
    assert response.status_code == _HTTP_OK
    payload = response.json()
    assert payload["status"] == "abstained"
    assert payload["robustness_surface"] is None
    assert payload["safe_failure_report"]["abstained"] is True


def test_typer_export_validate_challenge_verify_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    schema_path = tmp_path / "request-schema.json"
    exported = runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)])
    assert exported.exit_code == 0
    assert json.loads(schema_path.read_text(encoding="utf-8"))["x-glio-contract"]["moduleId"] == (
        "GLIO-PROTEOGEN-M24-06"
    )
    assert (
        runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)]).exit_code
        != 0
    )
    request_path = tmp_path / "request.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code == 0
    result_path = tmp_path / "result.json"
    challenged = runner.invoke(
        cli_app, ["challenge", str(request_path), "--output", str(result_path)]
    )
    assert challenged.exit_code == 0
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True


def test_typer_abstention_and_hostile_input_are_non_success(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "unsupported.json"
    request_path.write_text(unsupported_request().model_dump_json(), encoding="utf-8")
    result_path = tmp_path / "unsupported-result.json"
    result = runner.invoke(cli_app, ["challenge", str(request_path), "--output", str(result_path)])
    assert result.exit_code == 1
    assert result_path.exists()
    hostile = tmp_path / "hostile.json"
    hostile.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["validate", str(hostile)]).exit_code != 0
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0


__all__ = []

"""FastAPI, Typer, and plugin parity tests for provisional M24-04."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material.m24_04_external_transport_evaluator import (
    M2404Service,
    cli_app,
    create_app,
)
from tests.contract.test_m24_04_hardening import _request

if TYPE_CHECKING:
    from pathlib import Path

_SCHEMA_COUNT = 8
_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422
_HTTP_NOT_FOUND = 404


def test_fastapi_schema_validate_evaluate_and_verify_parity() -> None:
    client = TestClient(create_app(M2404Service()))
    schemas = client.get("/v1/modules/M24-04/schemas")
    assert schemas.status_code == _HTTP_OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    request_json = _request().model_dump_json()
    validated = client.post("/v1/modules/M24-04/validate", content=request_json)
    assert validated.status_code == _HTTP_OK
    evaluated = client.post("/v1/modules/M24-04/evaluate", content=request_json)
    assert evaluated.status_code == _HTTP_OK
    result = evaluated.json()
    verified = client.post("/v1/modules/M24-04/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True


def test_fastapi_sanitizes_non_object_and_unknown_schema_errors() -> None:
    client = TestClient(create_app(M2404Service()))
    malformed = client.post("/v1/modules/M24-04/validate", content=b"[]")
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in malformed.text
    unknown = client.get("/v1/modules/M24-04/schemas/unknown")
    assert unknown.status_code == _HTTP_NOT_FOUND
    replay = client.post("/v1/modules/M24-04/verify", content=b"[]")
    assert replay.status_code == _HTTP_UNPROCESSABLE


def test_typer_export_validate_evaluate_verify_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    schema_path = tmp_path / "request-schema.json"
    exported = runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)])
    assert exported.exit_code == 0
    assert json.loads(schema_path.read_text(encoding="utf-8"))["x-glio-contract"]["moduleId"] == (
        "GLIO-PROTEOGEN-M24-04"
    )
    assert (
        runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)]).exit_code
        != 0
    )
    request_path = tmp_path / "request.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code == 0
    result_path = tmp_path / "result.json"
    evaluated = runner.invoke(
        cli_app, ["evaluate", str(request_path), "--output", str(result_path)]
    )
    assert evaluated.exit_code == 0
    assert result_path.exists()
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True


def test_typer_rejects_hostile_json_without_traceback(tmp_path: Path) -> None:
    hostile = tmp_path / "hostile.json"
    hostile.write_bytes(b"[]")
    result = CliRunner().invoke(cli_app, ["validate", str(hostile)])
    assert result.exit_code != 0
    assert "Traceback" not in result.stdout


__all__ = []

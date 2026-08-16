"""FastAPI, Typer and strict-plugin parity tests for M21-05."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_complex_activity.m21_05_subgroup_equity_evaluator import (
    M2105Plugin,
    M2105Service,
    cli_app,
    create_app,
)
from tests.contract.test_m21_05_adversarial import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_fastapi_schema_validate_evaluate_verify_and_sanitized_errors() -> None:
    request = _request()
    client = TestClient(create_app(M2105Service()))
    schemas = client.get("/v1/modules/M21-05/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == {
        "request",
        "output",
        "report",
        "performance",
        "calibration",
        "coverage",
        "configuration",
        "finding",
    }
    body = request.model_dump(mode="json")
    assert client.post("/v1/modules/M21-05/validate", json=body).status_code == _HTTP_OK
    evaluated = client.post("/v1/modules/M21-05/evaluate", json=body)
    assert evaluated.status_code == _HTTP_OK
    verified = client.post("/v1/modules/M21-05/verify", json={"result": evaluated.json()})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M21-05/schemas/unknown").status_code == _HTTP_NOT_FOUND
    invalid = client.post("/v1/modules/M21-05/validate", content=b"[]")
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in invalid.text
    assert client.post("/v1/modules/M21-05/verify", json={"result": {}}).status_code == (
        _HTTP_UNPROCESSABLE
    )


def test_plugin_is_strict_parse_once_and_requires_execution_token() -> None:
    request = _request()
    plugin = M2105Plugin(M2105Service())
    validated = plugin.validate(request.model_dump_json())
    result = plugin.run(validated)
    assert result.status.value == "evaluated"
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M21-05"
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(object())
    with pytest.raises(TypeError):
        plugin.run(cast("Any", request))


def test_typer_export_validate_evaluate_verify_and_no_overwrite(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    schema_path = tmp_path / "schema.json"
    runner = CliRunner()
    assert (
        runner.invoke(
            cli_app,
            ["export-schema", "request", "--output", str(schema_path)],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli_app,
            ["export-schema", "request", "--output", str(schema_path)],
        ).exit_code
        != 0
    )
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code == 0
    result_path = tmp_path / "result.json"
    assert (
        runner.invoke(
            cli_app,
            ["evaluate", str(request_path), "--output", str(result_path)],
        ).exit_code
        == 0
    )
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert '"verified": true' in verified.stdout

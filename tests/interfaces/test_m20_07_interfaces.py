"""FastAPI, Typer and plugin parity tests for M20-07."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m20_07 import (
    M2007_MAX_CANONICAL_REQUEST_BYTES,
    M2007_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c20_biomarker_panel.m20_07_downstream_typed_export import (
    M2007Plugin,
    M2007Service,
    cli_app,
    create_app,
)
from tests.contract.test_m20_07_hardening import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_fastapi_schema_validate_export_verify_and_sanitized_errors() -> None:
    request = _request()
    client = TestClient(create_app(M2007Service()))
    schemas = client.get("/v1/modules/M20-07/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == {
        "request",
        "output",
        "contract",
        "field",
        "signature",
        "configuration",
        "finding",
        "ownership",
    }
    body = request.model_dump(mode="json")
    assert client.post("/v1/modules/M20-07/validate", json=body).status_code == _HTTP_OK
    exported = client.post("/v1/modules/M20-07/export", json=body)
    assert exported.status_code == _HTTP_OK
    verified = client.post("/v1/modules/M20-07/verify", json={"result": exported.json()})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M20-07/schemas/unknown").status_code == _HTTP_NOT_FOUND
    invalid = client.post("/v1/modules/M20-07/validate", content=b"[]")
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in invalid.text
    assert client.post("/v1/modules/M20-07/verify", json={"result": {}}).status_code == (
        _HTTP_UNPROCESSABLE
    )


def test_plugin_is_strict_parse_once_and_requires_execution_token() -> None:
    request = _request()
    plugin = M2007Plugin(M2007Service())
    validated = plugin.validate(request.model_dump_json())
    result = plugin.run(validated)
    assert result.status.value == "exported"
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M20-07"
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(object())
    with pytest.raises(TypeError):
        plugin.run(cast("Any", request))


def test_typer_export_validate_verify_and_no_overwrite(tmp_path: Any) -> None:
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
            ["export", str(request_path), "--output", str(result_path)],
        ).exit_code
        == 0
    )
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert '"verified": true' in verified.stdout


def test_typer_rejects_oversized_request_and_result_before_parse(tmp_path: Any) -> None:
    request_path = tmp_path / "oversized-request.json"
    result_path = tmp_path / "oversized-result.json"
    for path, limit in (
        (request_path, M2007_MAX_CANONICAL_REQUEST_BYTES),
        (result_path, M2007_MAX_CANONICAL_RESULT_BYTES),
    ):
        with path.open("wb") as stream:
            stream.seek(limit)
            stream.write(b"{}")
    runner = CliRunner()
    request_failure = runner.invoke(cli_app, ["validate", str(request_path)])
    result_failure = runner.invoke(cli_app, ["verify", str(result_path)])
    assert request_failure.exit_code != 0
    assert result_failure.exit_code != 0
    assert "Traceback" not in request_failure.output + result_failure.output

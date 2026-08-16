"""FastAPI, Typer, and plugin parity tests for provisional M21-03."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material.m21_03_internal_benchmark_ablation import (
    BenchmarkSubmission,
    M2103Plugin,
    M2103Service,
    cli_app,
    create_app,
)
from tests.contract.test_m21_03_provisional import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_fastapi_validate_benchmark_verify_and_sanitized_errors() -> None:
    request = _request()
    client = TestClient(create_app(M2103Service()))
    schemas = client.get("/v1/modules/M21-03/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == {
        "request",
        "output",
        "dossier",
        "split",
        "baseline",
        "metric",
        "ablation",
        "comparison",
        "finding",
    }
    body = request.model_dump(mode="json")
    assert client.post("/v1/modules/M21-03/validate", json=body).status_code == _HTTP_OK
    generated = client.post("/v1/modules/M21-03/benchmark", json=body)
    assert generated.status_code == _HTTP_OK
    result = generated.json()
    verified = client.post("/v1/modules/M21-03/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M21-03/schemas/unknown").status_code == _HTTP_NOT_FOUND
    assert (
        client.post("/v1/modules/M21-03/validate", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    malformed = client.post("/v1/modules/M21-03/verify", content=b"[")
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in malformed.text


def test_plugin_is_strict_parse_once_and_requires_token() -> None:
    request = _request()
    plugin = M2103Plugin(M2103Service())
    validated = plugin.validate(BenchmarkSubmission(request=request.model_dump_json()))
    result = plugin.run(validated)
    assert plugin.replay(result).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M21-03"
    with pytest.raises(TypeError, match="benchmark submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_typer_export_validate_benchmark_verify_and_no_overwrite(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    schema_path = tmp_path / "schema.json"
    result_path = tmp_path / "result.json"
    runner = CliRunner()
    assert (
        runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)]).exit_code
        == 0
    )
    assert (
        runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)]).exit_code
        != 0
    )
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_app, ["benchmark", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_app, ["benchmark", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )

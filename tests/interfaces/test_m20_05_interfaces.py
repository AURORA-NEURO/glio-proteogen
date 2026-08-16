"""FastAPI, Typer and plugin parity tests for M20-05."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c20_biomarker_panel.m20_05_workflow_presentation_service import (
    M2005Plugin,
    M2005Service,
    WorkflowPresentationSubmission,
    cli_app,
    create_app,
)
from tests.contract.test_m20_05_adversarial import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_fastapi_schema_validate_present_verify_and_sanitized_errors() -> None:
    request = _request()
    client = TestClient(create_app(M2005Service()))
    schemas = client.get("/v1/modules/M20-05/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == {
        "request",
        "output",
        "review-item",
        "next-action",
        "workspace",
        "configuration",
        "policy",
        "finding",
    }
    body = request.model_dump(mode="json")
    assert client.post("/v1/modules/M20-05/validate", json=body).status_code == _HTTP_OK
    presented = client.post("/v1/modules/M20-05/present", json=body)
    assert presented.status_code == _HTTP_OK
    result = presented.json()
    verified = client.post("/v1/modules/M20-05/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M20-05/schemas/unknown").status_code == _HTTP_NOT_FOUND
    invalid = client.post("/v1/modules/M20-05/validate", content=b"[]")
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in invalid.text


def test_plugin_is_strict_parse_once_and_requires_execution_token() -> None:
    request = _request()
    plugin = M2005Plugin(M2005Service())
    validated = plugin.validate(WorkflowPresentationSubmission(request=request.model_dump_json()))
    result = plugin.run(validated)
    assert result.status.value == "presented"
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M20-05"
    with pytest.raises(TypeError, match="workflow presentation submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_typer_export_validate_present_verify_and_no_overwrite(tmp_path: Any) -> None:
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
            ["present", str(request_path), "--output", str(result_path)],
        ).exit_code
        == 0
    )
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert '"verified": true' in verified.stdout

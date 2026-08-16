"""FastAPI, Typer and plugin parity tests for M20-06."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c20_biomarker_panel.m20_06_reviewer_discrepancy_adjudication import (
    AdjudicationSubmission,
    M2006Plugin,
    M2006Service,
    cli_app,
    create_app,
)
from tests.contract.test_m20_06_adversarial import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def _denied_request() -> Any:
    request = _request()
    denied_support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(update={"support": denied_support})
        }
    )
    return request.model_copy(update={"context": context})


def test_fastapi_schema_validate_adjudicate_verify_and_sanitized_errors() -> None:
    request = _request()
    client = TestClient(create_app(M2006Service()))
    schemas = client.get("/v1/modules/M20-06/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == {
        "request",
        "output",
        "record",
        "queue-entry",
        "assignment",
        "audit-event",
        "configuration",
        "finding",
    }
    body = request.model_dump(mode="json")
    assert client.post("/v1/modules/M20-06/validate", json=body).status_code == _HTTP_OK
    adjudicated = client.post("/v1/modules/M20-06/adjudicate", json=body)
    assert adjudicated.status_code == _HTTP_OK
    verified = client.post("/v1/modules/M20-06/verify", json={"result": adjudicated.json()})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M20-06/schemas/unknown").status_code == _HTTP_NOT_FOUND
    invalid = client.post("/v1/modules/M20-06/validate", content=b"[]")
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in invalid.text
    assert (
        client.post(
            "/v1/modules/M20-06/adjudicate", json=_denied_request().model_dump(mode="json")
        ).status_code
        == _HTTP_UNPROCESSABLE
    )
    assert client.post("/v1/modules/M20-06/verify", json={"result": {}}).status_code == (
        _HTTP_UNPROCESSABLE
    )


def test_plugin_is_strict_parse_once_and_requires_execution_token() -> None:
    request = _request()
    plugin = M2006Plugin(M2006Service())
    validated = plugin.validate(AdjudicationSubmission(request=request.model_dump_json()))
    result = plugin.run(validated)
    assert result.status.value == "recorded"
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M20-06"
    with pytest.raises(TypeError, match="adjudication submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_typer_export_validate_adjudicate_verify_and_no_overwrite(tmp_path: Any) -> None:
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
            ["adjudicate", str(request_path), "--output", str(result_path)],
        ).exit_code
        == 0
    )
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert '"verified": true' in verified.stdout

    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(canonical_json_bytes(_denied_request()))
    assert runner.invoke(cli_app, ["validate", str(denied_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["adjudicate", str(denied_path)]).exit_code != 0

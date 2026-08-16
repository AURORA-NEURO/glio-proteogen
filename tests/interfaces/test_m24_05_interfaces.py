"""FastAPI, Typer, and plugin parity tests for provisional M24-05."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material import (
    m24_05_subgroup_equity_evaluator as m2405,
)
from tests.contract.test_m24_05_hardening import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_CONTRACT_NAMES = {
    "request",
    "output",
    "report",
    "performance",
    "calibration",
    "coverage",
    "configuration",
    "finding",
}


def test_fastapi_validate_evaluate_verify_and_sanitized_errors() -> None:
    request = _request()
    client = TestClient(m2405.create_app(m2405.M2405Service()))
    schemas = client.get("/v1/modules/M24-05/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == _CONTRACT_NAMES
    body = request.model_dump(mode="json")
    assert client.post("/v1/modules/M24-05/validate", json=body).status_code == _HTTP_OK
    evaluated = client.post("/v1/modules/M24-05/evaluate", json=body)
    assert evaluated.status_code == _HTTP_OK
    verified = client.post("/v1/modules/M24-05/verify", json={"result": evaluated.json()})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M24-05/schemas/unknown").status_code == _HTTP_NOT_FOUND
    assert client.get("/v1/modules/M24-05/schemas/request").status_code == _HTTP_OK
    malformed = client.post("/v1/modules/M24-05/verify", content=b"[")
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert client.post("/v1/modules/M24-05/validate", json=[]).status_code == _HTTP_UNPROCESSABLE
    assert client.post("/v1/modules/M24-05/verify", json=[]).status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in malformed.text


def test_fastapi_denied_controls_are_sanitized() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"support": support})
    denied = request.model_copy(
        update={"context": request.context.model_copy(update={"references": references})}
    )
    client = TestClient(m2405.create_app(m2405.M2405Service()))
    response = client.post("/v1/modules/M24-05/evaluate", json=denied.model_dump(mode="json"))
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text


def test_plugin_is_strict_parse_once_and_requires_token() -> None:
    request = _request()
    plugin = m2405.M2405Plugin(m2405.M2405Service())
    validated = plugin.validate(
        m2405.SubgroupEvaluationSubmission(request=request.model_dump_json())
    )
    result = plugin.run(validated)
    assert plugin.replay(result).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M24-05"
    with pytest.raises(TypeError, match="subgroup-evaluation submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_typer_export_evaluate_verify_and_no_overwrite(tmp_path: Any) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    schema_path = tmp_path / "schema.json"
    result_path = tmp_path / "result.json"
    runner = CliRunner()
    assert runner.invoke(m2405.cli.app, ["export-schema", "request"]).exit_code == 0
    assert (
        runner.invoke(
            m2405.cli.app, ["export-schema", "request", "--output", str(schema_path)]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            m2405.cli.app, ["export-schema", "request", "--output", str(schema_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m2405.cli.app, ["validate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            m2405.cli.app, ["evaluate", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    assert runner.invoke(m2405.cli.app, ["verify", str(result_path)]).exit_code == 0
    assert (
        runner.invoke(
            m2405.cli.app, ["evaluate", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert m2405.M2405Service.export_json(m2405.M2405Service().evaluate(_request()))


def test_typer_sanitizes_bad_inputs(tmp_path: Any) -> None:
    runner = CliRunner()
    assert runner.invoke(m2405.cli.app, ["export-schema", "unknown"]).exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    assert runner.invoke(m2405.cli.app, ["validate", str(bad_request)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"[]")
    assert runner.invoke(m2405.cli.app, ["verify", str(bad_result)]).exit_code != 0

"""FastAPI, Typer, and plugin parity tests for provisional M23-05."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m23_05 import CoverageStatus
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m23_05_subgroup_equity_evaluator import (
    EquityEvaluationSubmission,
    M2305Plugin,
    M2305Service,
    cli_app,
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m23_05_subgroup_equity_evaluator import (
    cli as cli_module,
)
from tests.contract.test_m23_05_hardening import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_fastapi_validate_evaluate_verify_and_sanitized_errors() -> None:
    request = _request()
    client = TestClient(create_app(M2305Service()))
    schemas = client.get("/v1/modules/M23-05/schemas")
    assert schemas.status_code == _HTTP_OK
    assert client.get("/v1/modules/M23-05/schemas/request").status_code == _HTTP_OK
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
    assert client.post("/v1/modules/M23-05/validate", json=body).status_code == _HTTP_OK
    generated = client.post("/v1/modules/M23-05/evaluate", json=body)
    assert generated.status_code == _HTTP_OK
    verified = client.post("/v1/modules/M23-05/verify", json={"result": generated.json()})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M23-05/schemas/unknown").status_code == _HTTP_NOT_FOUND
    assert (
        client.post("/v1/modules/M23-05/validate", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    malformed = client.post("/v1/modules/M23-05/verify", content=b"[")
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert client.post("/v1/modules/M23-05/verify", json={}).status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in malformed.text


def test_fastapi_unsupported_coverage_is_explicit_abstention() -> None:
    request = _request()
    unsupported = request.coverage[0].model_copy(update={"status": CoverageStatus.UNSUPPORTED})
    payload = request.model_copy(
        update={"coverage": (unsupported, *request.coverage[1:])}
    ).model_dump(mode="json")
    response = TestClient(create_app(M2305Service())).post(
        "/v1/modules/M23-05/evaluate", json=payload
    )
    assert response.status_code == _HTTP_OK
    assert response.json()["status"] == "abstained"
    assert response.json()["report"] is None


def test_fastapi_denied_controls_are_sanitized() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    denied = request.model_copy(update={"context": context}).model_dump(mode="json")
    client = TestClient(create_app(M2305Service()))
    validate_response = client.post("/v1/modules/M23-05/validate", json=denied)
    evaluate_response = client.post("/v1/modules/M23-05/evaluate", json=denied)
    assert validate_response.status_code == _HTTP_UNPROCESSABLE
    assert evaluate_response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in evaluate_response.text


def test_plugin_is_strict_parse_once_and_requires_token() -> None:
    request = _request()
    plugin = M2305Plugin(M2305Service())
    validated = plugin.validate(EquityEvaluationSubmission(request=request.model_dump_json()))
    result = plugin.run(validated)
    assert plugin.replay(result).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M23-05"
    with pytest.raises(TypeError, match="equity submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_typer_export_validate_evaluate_verify_and_no_overwrite(tmp_path: Path) -> None:
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
    assert runner.invoke(cli_app, ["evaluate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_app, ["evaluate", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_app, ["evaluate", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )


def test_typer_sanitizes_bad_inputs_and_replay_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["validate", str(bad_request)]).exit_code != 0
    assert runner.invoke(cli_app, ["evaluate", str(bad_request)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["verify", str(bad_result)]).exit_code != 0
    result_path = tmp_path / "valid-result.json"
    result_path.write_bytes(canonical_json_bytes(M2305Service().evaluate(_request())))

    class ReplayFailure:
        def replay(self, _result: object) -> object:
            raise ValueError

    monkeypatch.setattr(cli_module, "_SERVICE", ReplayFailure())
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0

"""FastAPI, Typer, and plugin parity tests for provisional M24-02."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m24_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2402Plugin,
    M2402Service,
    SyntheticTruthSubmission,
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m24_02_synthetic_truth_simulation_generator import (  # noqa: E501
    cli as cli_module,
)
from tests.contract.test_m24_02_hardening import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_CONTRACT_NAMES = {"request", "output", "corpus", "case", "manifest", "configuration", "finding"}


def test_fastapi_validate_generate_verify_and_sanitized_errors() -> None:
    request = _request()
    client = TestClient(create_app(M2402Service()))
    schemas = client.get("/v1/modules/M24-02/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == _CONTRACT_NAMES
    body = request.model_dump(mode="json")
    assert client.post("/v1/modules/M24-02/validate", json=body).status_code == _HTTP_OK
    generated = client.post("/v1/modules/M24-02/generate", json=body)
    assert generated.status_code == _HTTP_OK
    verified = client.post("/v1/modules/M24-02/verify", json={"result": generated.json()})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M24-02/schemas/unknown").status_code == _HTTP_NOT_FOUND
    assert client.get("/v1/modules/M24-02/schemas/request").status_code == _HTTP_OK
    malformed = client.post("/v1/modules/M24-02/verify", content=b"[")
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert client.post("/v1/modules/M24-02/validate", json=[]).status_code == _HTTP_UNPROCESSABLE
    assert client.post("/v1/modules/M24-02/verify", json=[]).status_code == _HTTP_UNPROCESSABLE
    assert client.post("/v1/modules/M24-02/verify", json={}).status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in malformed.text


def test_fastapi_denied_controls_are_sanitized() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    denied = request.model_copy(update={"context": context}).model_dump(mode="json")
    response = TestClient(create_app(M2402Service())).post(
        "/v1/modules/M24-02/generate", json=denied
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    validate = TestClient(create_app(M2402Service())).post(
        "/v1/modules/M24-02/validate", json=denied
    )
    assert validate.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in response.text


def test_plugin_is_strict_parse_once_and_requires_token() -> None:
    request = _request()
    plugin = M2402Plugin(M2402Service())
    validated = plugin.validate(SyntheticTruthSubmission(request=request.model_dump_json()))
    result = plugin.run(validated)
    assert plugin.replay(result).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M24-02"
    with pytest.raises(TypeError, match="synthetic-truth submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_typer_export_generate_verify_and_no_overwrite(tmp_path: Any) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    schema_path = tmp_path / "schema.json"
    result_path = tmp_path / "result.json"
    runner = CliRunner()
    assert runner.invoke(cli_module.app, ["export-schema", "request"]).exit_code == 0
    assert (
        runner.invoke(
            cli_module.app, ["export-schema", "request", "--output", str(schema_path)]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli_module.app, ["export-schema", "request", "--output", str(schema_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(cli_module.app, ["validate", str(request_path)]).exit_code == 0
    assert runner.invoke(cli_module.app, ["generate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_module.app, ["generate", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    assert runner.invoke(cli_module.app, ["verify", str(result_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_module.app, ["generate", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert M2402Service.export_json(M2402Service().generate(_request()))


def test_typer_sanitizes_bad_inputs_and_replay_failures(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    assert runner.invoke(cli_module.app, ["export-schema", "unknown"]).exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    assert runner.invoke(cli_module.app, ["validate", str(bad_request)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"[]")
    assert runner.invoke(cli_module.app, ["verify", str(bad_result)]).exit_code != 0
    result_path = tmp_path / "valid-result.json"
    result_path.write_bytes(canonical_json_bytes(M2402Service().generate(_request())))

    class ReplayFailure:
        def verify_replay(self, _result: object) -> object:
            raise ValueError("replay failure")  # noqa: TRY003

    monkeypatch.setattr(cli_module, "_SERVICE", ReplayFailure())
    assert runner.invoke(cli_module.app, ["verify", str(result_path)]).exit_code != 0

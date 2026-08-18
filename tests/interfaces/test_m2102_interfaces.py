"""FastAPI, Typer and plugin parity tests for M21-02."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m21_02.fixture import build_request, denied_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c21_reference_material.m21_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2102Plugin,
    M2102Service,
    SyntheticTruthSubmission,
    cli_app,
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m21_02_synthetic_truth_simulation_generator import (  # noqa: E501
    cli as cli_module,
)

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_fastapi_validate_generate_verify_and_sanitized_errors() -> None:
    request = build_request()
    client = TestClient(create_app(M2102Service()))
    schemas = client.get("/v1/modules/M21-02/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == {
        "request",
        "output",
        "corpus",
        "case",
        "manifest",
        "configuration",
        "finding",
    }
    assert client.get("/v1/modules/M21-02/schemas/request").status_code == _HTTP_OK
    body = request.model_dump(mode="json")
    assert client.post("/v1/modules/M21-02/validate", json=body).status_code == _HTTP_OK
    generated = client.post("/v1/modules/M21-02/generate", json=body)
    assert generated.status_code == _HTTP_OK
    result = generated.json()
    verified = client.post("/v1/modules/M21-02/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M21-02/schemas/unknown").status_code == _HTTP_NOT_FOUND
    assert client.post("/v1/modules/M21-02/validate", content=b"[]").status_code == (
        _HTTP_UNPROCESSABLE
    )
    assert client.post("/v1/modules/M21-02/verify", content=b"[").status_code == (
        _HTTP_UNPROCESSABLE
    )
    assert client.post("/v1/modules/M21-02/verify", content=b"[]").status_code == (
        _HTTP_UNPROCESSABLE
    )
    denied_validation = client.post(
        "/v1/modules/M21-02/validate", json=denied_request().model_dump(mode="json")
    )
    assert denied_validation.status_code == _HTTP_UNPROCESSABLE
    denied = client.post(
        "/v1/modules/M21-02/generate", json=denied_request().model_dump(mode="json")
    )
    assert denied.status_code == _HTTP_UNPROCESSABLE
    invalid_replay = client.post("/v1/modules/M21-02/verify", json={"result": {}})
    assert invalid_replay.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in invalid_replay.text


def test_plugin_is_strict_parse_once_and_requires_execution_token() -> None:
    request = build_request()
    plugin = M2102Plugin(M2102Service())
    validated = plugin.validate(SyntheticTruthSubmission(request=request.model_dump_json()))
    result = plugin.run(validated)
    assert plugin.replay(result).result_digest == result.result_digest
    assert result.status.value == "generated"
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M21-02"
    with pytest.raises(TypeError, match="synthetic-truth submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_typer_export_validate_generate_verify_and_no_overwrite(tmp_path: Any) -> None:
    request = build_request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    schema_path = tmp_path / "schema.json"
    runner = CliRunner()
    export = runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)])
    assert export.exit_code == 0
    overwrite = runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)])
    assert overwrite.exit_code != 0
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code == 0
    result_path = tmp_path / "result.json"
    generated = runner.invoke(
        cli_app, ["generate", str(request_path), "--output", str(result_path)]
    )
    assert generated.exit_code == 0
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code == 0
    overwrite_result = runner.invoke(
        cli_app, ["generate", str(request_path), "--output", str(result_path)]
    )
    assert overwrite_result.exit_code != 0


def test_typer_sanitizes_bad_inputs_and_replay_outcomes(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(cli_app, ["export-schema", "request"]).exit_code == 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["validate", str(bad_request)]).exit_code != 0
    assert runner.invoke(cli_app, ["generate", str(bad_request)]).exit_code != 0
    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(canonical_json_bytes(denied_request()))
    assert runner.invoke(cli_app, ["validate", str(denied_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["generate", str(denied_path)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["verify", str(bad_result)]).exit_code != 0

    request = build_request()
    result_path = tmp_path / "result.json"
    result_path.write_bytes(canonical_json_bytes(M2102Service().generate(request)))

    class ReplayFailure:
        def replay(self, _result: object) -> object:
            raise ValueError

    monkeypatch.setattr(cli_module, "_SERVICE", ReplayFailure())
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0

    valid_result = M2102Service().generate(request)

    class ReplayMismatch:
        def replay(self, _result: object) -> object:
            return valid_result.model_copy(update={"result_digest": sha256_digest("mismatch")})

    monkeypatch.setattr(cli_module, "_SERVICE", ReplayMismatch())
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code == 1

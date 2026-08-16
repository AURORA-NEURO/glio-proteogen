"""FastAPI, Typer, and plugin parity tests for provisional M21-06."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material.m21_06_robustness_shift_ood_challenge import (
    M2106Plugin,
    M2106Service,
    RobustnessSubmission,
    cli_app,
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m21_06_robustness_shift_ood_challenge import (
    cli as cli_module,
)
from tests.adversarial.test_m2106_adversarial import _request
from tests.runtime.test_m2106_runtime import _supported_request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_CONTRACT_NAMES = {
    "request",
    "output",
    "surface",
    "scenario",
    "observation",
    "safe-failure",
    "configuration",
    "finding",
}


def test_fastapi_validate_challenge_verify_and_sanitized_errors() -> None:
    request = _supported_request()
    client = TestClient(create_app(M2106Service()))
    schemas = client.get("/v1/modules/M21-06/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == _CONTRACT_NAMES
    body = request.model_dump(mode="json")
    assert client.post("/v1/modules/M21-06/validate", json=body).status_code == _HTTP_OK
    generated = client.post("/v1/modules/M21-06/challenge", json=body)
    assert generated.status_code == _HTTP_OK
    result = generated.json()
    verified = client.post("/v1/modules/M21-06/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M21-06/schemas/unknown").status_code == _HTTP_NOT_FOUND
    assert (
        client.post("/v1/modules/M21-06/validate", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    malformed = client.post("/v1/modules/M21-06/verify", content=b"[")
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert client.post("/v1/modules/M21-06/verify", json={}).status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in malformed.text


def test_fastapi_unsupported_request_is_safe_abstention() -> None:
    request = _request()
    client = TestClient(create_app(M2106Service()))
    response = client.post("/v1/modules/M21-06/challenge", json=request.model_dump(mode="json"))
    assert response.status_code == _HTTP_OK
    result = response.json()
    assert result["status"] == "abstained"
    assert result["robustness_surface"] is None


def test_plugin_is_strict_parse_once_and_requires_token() -> None:
    request = _supported_request()
    plugin = M2106Plugin(M2106Service())
    validated = plugin.validate(RobustnessSubmission(request=request.model_dump_json()))
    result = plugin.run(validated)
    assert plugin.replay(result).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M21-06"
    with pytest.raises(TypeError, match="robustness submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_typer_export_validate_challenge_verify_and_no_overwrite(tmp_path: Path) -> None:
    request = _supported_request()
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
    assert runner.invoke(cli_app, ["challenge", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_app, ["challenge", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_app, ["challenge", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )


def test_typer_sanitizes_bad_inputs_and_replay_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["validate", str(bad_request)]).exit_code != 0
    assert runner.invoke(cli_app, ["challenge", str(bad_request)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["verify", str(bad_result)]).exit_code != 0
    request = _supported_request()
    result_path = tmp_path / "valid-result.json"
    result_path.write_bytes(canonical_json_bytes(M2106Service().generate(request)))

    class ReplayFailure:
        def replay(self, _result: object) -> object:
            raise ValueError

    monkeypatch.setattr(cli_module, "_SERVICE", ReplayFailure())
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0

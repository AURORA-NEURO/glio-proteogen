"""API, CLI, and plugin parity tests for M12-02."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import m1202 as m1202_adapter
from glio_proteogen.adapters.m1202 import app, m1202_app
from glio_proteogen.contracts.m12_02 import (
    BiomarkerPanelContextStratificationResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c12_driver_to_protein_consequence import (
    m12_02_context_subtype_stratifier,
)
from tests.contract.test_m12_02_contract import _request

_CLIENT = TestClient(app)
_RUNNER = CliRunner()
_OK = 200
_NOT_FOUND = 404
_UNSUPPORTED_MEDIA = 415
_INVALID = 422
_FORBIDDEN = 403
M1202Plugin = m12_02_context_subtype_stratifier.M1202Plugin
M1202Service = m12_02_context_subtype_stratifier.M1202Service


def _payload() -> dict[str, object]:
    return _request().model_dump(mode="json")


def test_api_schema_and_context_endpoint() -> None:
    schema_response = _CLIENT.get("/v1/m12-02/schema/request")
    assert schema_response.status_code == _OK
    assert schema_response.json()["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M12-02"

    response = _CLIENT.post("/v1/modules/M12-02/context", json=_payload())
    assert response.status_code == _OK
    assert response.json()["status"] == "stratified"


def test_api_rejects_wrong_content_type_and_unknown_schema() -> None:
    assert _CLIENT.get("/v1/m12-02/schema/unknown").status_code == _NOT_FOUND
    response = _CLIENT.post(
        "/v1/modules/M12-02/context",
        content=json.dumps(_payload()),
        headers={"content-type": "text/plain"},
    )
    assert response.status_code == _UNSUPPORTED_MEDIA


def test_api_verification_replays_result_and_rejects_tamper() -> None:
    response = _CLIENT.post("/v1/modules/M12-02/context", json=_payload())
    assert response.status_code == _OK
    verified = _CLIENT.post(
        "/v1/modules/M12-02/verify",
        json=response.json(),
    )
    assert verified.status_code == _OK
    assert verified.json() == response.json()
    tampered = dict(response.json())
    tampered["result_digest"] = "sha256:" + ("b" * 64)
    assert _CLIENT.post("/v1/modules/M12-02/verify", json=tampered).status_code == _INVALID


def test_api_authorizes_before_invalid_observation_traversal() -> None:
    payload = _payload()
    payload["context"]["references"]["support"]["state"] = "rejected"  # type: ignore[index]
    payload["observations"] = []
    response = _CLIENT.post("/v1/modules/M12-02/context", json=payload)
    assert response.status_code in {_FORBIDDEN, _INVALID}
    if response.status_code == _FORBIDDEN:
        assert "accepted controls" in response.json()["detail"]


def test_api_strict_json_and_validation_error_surfaces() -> None:
    invalid_json = _CLIENT.post(
        "/v1/modules/M12-02/context",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert invalid_json.status_code == _INVALID
    payload = _payload()
    del payload["observations"]
    invalid_model = _CLIENT.post("/v1/modules/M12-02/context", json=payload)
    assert invalid_model.status_code == _INVALID
    wrong_verify_type = _CLIENT.post(
        "/v1/modules/M12-02/verify",
        content=b"{}",
        headers={"content-type": "text/plain"},
    )
    assert wrong_verify_type.status_code == _UNSUPPORTED_MEDIA


def test_api_service_authorization_error_is_sanitized(monkeypatch) -> None:
    class FailingService:
        def _execute_validated(self, request):
            raise m1202_adapter.M1202ContextAuthorizationError

    monkeypatch.setattr(m1202_adapter, "_SERVICE", FailingService())
    response = _CLIENT.post("/v1/modules/M12-02/context", json=_payload())
    assert response.status_code == _FORBIDDEN


def test_cli_invalid_schema_request_and_verify_paths(tmp_path) -> None:
    unknown_schema = _RUNNER.invoke(m1202_app, ["export-schema", "unknown"])
    assert unknown_schema.exit_code == 2
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_text("{}", encoding="utf-8")
    failed_stratify = _RUNNER.invoke(m1202_app, ["stratify", str(bad_request)])
    assert failed_stratify.exit_code == 1
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("not-json", encoding="utf-8")
    failed_verify = _RUNNER.invoke(m1202_app, ["verify", str(bad_result)])
    assert failed_verify.exit_code == 1


def test_cli_stratify_stdout_and_plugin_service_seams(tmp_path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    stdout = _RUNNER.invoke(m1202_app, ["stratify", str(request_path)])
    assert stdout.exit_code == 0
    result_path = tmp_path / "result.json"
    result_path.write_text(stdout.stdout, encoding="utf-8")
    verified = _RUNNER.invoke(m1202_app, ["verify", str(result_path)])
    assert verified.exit_code == 0

    service = M1202Service()
    request = _request()
    assert service.validate_request(request) == request
    result = service.execute(request)
    assert service.verify(result, replay=False) == result


def test_cli_export_schema_and_stratify_no_overwrite(tmp_path) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(_request()))

    export = _RUNNER.invoke(m1202_app, ["export-schema", "output"])
    assert export.exit_code == 0
    assert json.loads(export.stdout)["$id"].endswith(":output")

    first = _RUNNER.invoke(
        m1202_app,
        ["stratify", str(request_path), "--output", str(output_path)],
    )
    assert first.exit_code == 0
    parsed = BiomarkerPanelContextStratificationResult.model_validate_json(
        output_path.read_bytes(), strict=True
    )
    assert parsed.status.value == "stratified"
    second = _RUNNER.invoke(
        m1202_app,
        ["stratify", str(request_path), "--output", str(output_path)],
    )
    assert second.exit_code != 0


def test_plugin_is_parse_once_and_token_bound() -> None:
    plugin = M1202Plugin(M1202Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M12-02"
    raw = canonical_json_bytes(_request())
    token = plugin.validate(raw)
    result = plugin.run(token)
    assert result.status.value == "stratified"
    assert plugin.run(plugin.validate(_request())).status.value == "stratified"
    assert plugin.verify(result, replay=False) == result
    with pytest.raises(TypeError):
        plugin.run(token.__class__(request=token.request, _seal=object()))
    with pytest.raises(StrictJsonError):
        strict_json_loads(b'{"request_id": 1, "request_id": 2}')

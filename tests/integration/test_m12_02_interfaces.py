"""API, CLI, and plugin parity tests for M12-02."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

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
    raw = canonical_json_bytes(_request())
    token = plugin.validate(raw)
    result = plugin.run(token)
    assert result.status.value == "stratified"
    with pytest.raises(TypeError):
        plugin.run(token.__class__(request=token.request, _seal=object()))
    with pytest.raises(StrictJsonError):
        strict_json_loads(b'{"request_id": 1, "request_id": 2}')

"""FastAPI, Typer, and plugin parity checks for M09-07."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m09_07 import verify_result_replay
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_07_calibration_selective_prediction as m0907,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_07_calibration_selective_prediction.cli import (  # noqa: E501
    app as cli_app,
)
from tests.contract.test_m09_07_contract_hardening import _request
from tests.modules.test_m09_07_runtime import _candidate

HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_UNPROCESSABLE = 422
HTTP_OK = 200
EXIT_FAILURE = 2


def _document() -> tuple[dict[str, object], object]:
    request = _request().model_copy(update={"candidate": _candidate()})
    return request.model_dump(mode="json"), request


def test_plugin_json_parity_and_replay_tamper_detection() -> None:
    document, request = _document()
    plugin = m0907.M0907Plugin(m0907.M0907Service())
    token = plugin.validate(json.dumps(document, separators=(",", ":")))
    result = plugin.run(token)
    assert result.status.value == "calibrated"
    assert m0907.M0907Service.verify(result, request)
    assert verify_result_replay(result, request)
    tampered = result.model_dump(mode="json")
    tampered["status"] = "abstained"
    assert not m0907.M0907Service.verify(tampered, request)


def test_plugin_rejects_invalid_json_and_forged_capability() -> None:
    plugin = m0907.M0907Plugin(m0907.M0907Service())
    with pytest.raises(StrictJsonError):
        plugin.validate('{"request_id":1,"request_id":2}')
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    document, _request_model = _document()
    token = plugin.validate(json.dumps(document, separators=(",", ":")))
    forged = m0907.ValidatedM0907Request(request=token.request, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)


def test_api_rejects_duplicate_json_keys_and_returns_schema() -> None:
    document, _ = _document()
    client = TestClient(m0907.create_app(m0907.M0907Service()))
    response = client.post("/m09-07/calibrate", content=b'{"request_id":1,"request_id":2}')
    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["error"]["type"] == "json_duplicate_key"
    schemas = client.get("/m09-07/schema")
    assert schemas.status_code == HTTP_OK
    assert schemas.json()["schemas"]["request"]["x-glio-contract"]["provisionalAbi"] is True
    assert client.post("/m09-07/calibrate", json=document).status_code == HTTP_OK


def test_api_sanitizes_auth_validation_and_verify_errors() -> None:
    client = TestClient(m0907.create_app(m0907.M0907Service()))
    unauthorized = client.post("/m09-07/calibrate", json={})
    assert unauthorized.status_code == HTTP_FORBIDDEN
    document, request = _document()
    invalid_document = dict(document)
    invalid_document["unknown"] = "secret-canary"
    invalid = client.post("/m09-07/calibrate", json=invalid_document)
    assert invalid.status_code == HTTP_UNPROCESSABLE
    assert "secret-canary" not in invalid.text
    result = m0907.M0907Service().execute(request)
    verified = client.post(
        "/m09-07/verify",
        json={"request": request.model_dump(mode="json"), "result": result.model_dump(mode="json")},
    )
    assert verified.status_code == HTTP_OK
    assert verified.json() == {"valid": True}
    assert client.post("/m09-07/verify", json=[]).json()["error"]["type"] == "invalid_document"
    malformed = client.post("/m09-07/verify", content=b"not-json")
    assert malformed.json()["error"]["type"] == "json_invalid_syntax"


def test_cli_schema_and_strict_validation(tmp_path) -> None:
    document, _ = _document()
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(document), encoding="utf-8")
    runner = CliRunner()
    exported = runner.invoke(cli_app, ["export-schema", "candidate"])
    assert exported.exit_code == 0
    assert '"provisionalAbi": true' in exported.stdout
    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["valid"] is True
    executed = runner.invoke(cli_app, ["calibrate", str(request_path)])
    assert executed.exit_code == 0
    assert json.loads(executed.stdout)["status"] == "calibrated"


def test_cli_rejects_invalid_input_unknown_schema_and_overwrite(tmp_path) -> None:
    runner = CliRunner()
    bad = tmp_path / "bad.json"
    bad.write_text("{bad", encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(bad)]).exit_code == EXIT_FAILURE
    assert runner.invoke(cli_app, ["calibrate", str(bad)]).exit_code == EXIT_FAILURE
    document, _ = _document()
    document["unknown"] = "canary"
    invalid_request = tmp_path / "invalid-request.json"
    invalid_request.write_text(json.dumps(document), encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(invalid_request)]).exit_code == EXIT_FAILURE
    assert runner.invoke(cli_app, ["calibrate", str(invalid_request)]).exit_code == EXIT_FAILURE
    unknown = runner.invoke(cli_app, ["export-schema", "secret-schema"])
    assert unknown.exit_code == EXIT_FAILURE
    existing = tmp_path / "schema.json"
    existing.write_text("existing", encoding="utf-8")
    overwrite = runner.invoke(cli_app, ["export-schema", "request", "--output", str(existing)])
    assert overwrite.exit_code == EXIT_FAILURE

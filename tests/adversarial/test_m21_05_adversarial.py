"""Adversarial transport, authorization and replay coverage for M21-05."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m21_05 import CoverageStatus
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c21_complex_activity.m21_05_subgroup_equity_evaluator import (
    M2105AuthorizationError,
    M2105Engine,
    M2105EvaluationError,
    M2105Plugin,
    M2105ReplayError,
    M2105Service,
    cli_app,
    create_app,
)
from tests.contract.test_m21_05_adversarial import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_preflight_rejects_missing_or_malformed_controls() -> None:
    engine = M2105Engine()
    with pytest.raises(M2105AuthorizationError):
        engine.evaluate({"context": {"references": {}}})
    with pytest.raises(M2105AuthorizationError):
        engine.evaluate(cast("Any", {"context": None}))


def test_preflight_rejects_mapping_control_state_without_traversal() -> None:
    request = _request().model_dump(mode="python")
    references = cast("dict[str, Any]", request["context"]["references"])
    references["support"] = {"state": "accepted"}
    with pytest.raises((M2105AuthorizationError, M2105EvaluationError)):
        M2105Engine().evaluate(request)


def test_plugin_rejects_invalid_json_and_unsealed_token() -> None:
    request = _request()
    plugin = M2105Plugin()
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(b'{"context": NaN}')
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(b"[]")
    with pytest.raises(TypeError):
        plugin.run(cast("Any", object()))
    token = plugin.validate(request)
    result = plugin.run(token)
    assert plugin.verify(result).result_digest == result.result_digest


def test_api_sanitizes_malformed_json_and_unknown_schema() -> None:
    client = TestClient(create_app(M2105Service()))
    malformed = client.post(
        "/v1/modules/M21-05/validate",
        content=b'{"context":',
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in malformed.text
    primitive = client.post(
        "/v1/modules/M21-05/validate",
        content=b"[]",
        headers={"content-type": "application/json"},
    )
    assert primitive.status_code == _HTTP_UNPROCESSABLE
    unknown = client.get("/v1/modules/M21-05/schemas/not-a-contract")
    assert unknown.status_code == _HTTP_NOT_FOUND
    assert client.get("/v1/modules/M21-05/schemas/request").status_code == _HTTP_OK
    malformed_envelope = client.post(
        "/v1/modules/M21-05/verify",
        content=b"{",
        headers={"content-type": "application/json"},
    )
    assert malformed_envelope.status_code == _HTTP_UNPROCESSABLE
    primitive_envelope = client.post(
        "/v1/modules/M21-05/verify",
        content=b"[]",
        headers={"content-type": "application/json"},
    )
    assert primitive_envelope.status_code == _HTTP_UNPROCESSABLE


def test_api_sanitizes_authorization_errors_for_validate_and_evaluate() -> None:
    request = _request()
    consent = request.context.references.consent.model_copy(update={"state": ConsentState.REVOKED})
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"consent": consent})}
    )
    denied = request.model_copy(update={"context": context}).model_dump(mode="json")
    client = TestClient(create_app())
    validate = client.post("/v1/modules/M21-05/validate", json=denied)
    evaluate = client.post("/v1/modules/M21-05/evaluate", json=denied)
    assert validate.status_code == _HTTP_UNPROCESSABLE
    assert evaluate.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in validate.text + evaluate.text


def test_cli_rejects_bad_input_and_preserves_existing_output(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "bad.json"
    request_path.write_bytes(b"[]")
    invalid = runner.invoke(cli_app, ["validate", str(request_path)])
    assert invalid.exit_code != 0
    assert "Traceback" not in invalid.stdout

    output = tmp_path / "schema.json"
    output.write_text("sentinel", encoding="utf-8")
    overwrite = runner.invoke(
        cli_app,
        ["export-schema", "request", "--output", str(output)],
    )
    assert overwrite.exit_code != 0
    assert output.read_text(encoding="utf-8") == "sentinel"
    unknown_schema = runner.invoke(cli_app, ["export-schema", "unknown"])
    assert unknown_schema.exit_code != 0

    result_path = tmp_path / "invalid-result.json"
    result_path.write_bytes(b"[]")
    invalid_result = runner.invoke(cli_app, ["verify", str(result_path)])
    assert invalid_result.exit_code != 0


def test_abstained_cli_result_is_nonzero_and_canonical(tmp_path: Path) -> None:
    request = _request()
    coverage = list(request.coverage)
    coverage[0] = coverage[0].model_copy(update={"status": CoverageStatus.UNSUPPORTED})
    unsafe = request.model_copy(update={"coverage": tuple(coverage)})
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(unsafe))
    result_path = tmp_path / "result.json"
    invocation = CliRunner().invoke(
        cli_app,
        ["evaluate", str(request_path), "--output", str(result_path)],
    )
    assert invocation.exit_code == 1
    assert result_path.exists()
    assert '"status":"abstained"' in result_path.read_text(encoding="utf-8")
    printed = CliRunner().invoke(cli_app, ["evaluate", str(request_path)])
    assert printed.exit_code == 1
    assert '"status":"abstained"' in printed.stdout


def test_api_rejects_tampered_result_digest() -> None:
    request = _request()
    result = M2105Engine().evaluate(request)
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    response = TestClient(create_app()).post(
        "/v1/modules/M21-05/verify",
        json={"result": tampered.model_dump(mode="json")},
    )
    assert response.status_code == _HTTP_UNPROCESSABLE


def test_replay_rejects_result_ownership_tamper() -> None:
    engine = M2105Engine()
    result = engine.evaluate(_request())
    tampered_request = _request().model_copy(update={"request_id": "request.m2105.other"})
    with pytest.raises(M2105ReplayError):
        engine.verify(result.model_copy(update={"request": tampered_request}), replay=False)

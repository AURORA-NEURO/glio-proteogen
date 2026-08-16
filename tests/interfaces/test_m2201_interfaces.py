"""FastAPI, Typer, and plugin parity tests for provisional M22-01."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m22_01 import AdjudicationStatus
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material.m22_01_reference_truth_benchmark_curator import (
    M2201Plugin,
    M2201Service,
    ReferenceTruthSubmission,
    cli_app,
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m22_01_reference_truth_benchmark_curator import (
    cli as cli_module,
)
from tests.adversarial.test_m2201_adversarial import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_CONTRACT_NAMES = {
    "request",
    "output",
    "reference",
    "endpoint",
    "inclusion",
    "adjudication",
    "configuration",
    "package",
    "finding",
}


def test_fastapi_validate_curate_verify_and_sanitized_errors() -> None:
    request = _request()
    client = TestClient(create_app(M2201Service()))
    schemas = client.get("/v1/modules/M22-01/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == _CONTRACT_NAMES
    body = request.model_dump(mode="json")
    assert client.post("/v1/modules/M22-01/validate", json=body).status_code == _HTTP_OK
    generated = client.post("/v1/modules/M22-01/curate", json=body)
    assert generated.status_code == _HTTP_OK
    verified = client.post("/v1/modules/M22-01/verify", json={"result": generated.json()})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M22-01/schemas/unknown").status_code == _HTTP_NOT_FOUND
    assert (
        client.post("/v1/modules/M22-01/validate", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    malformed = client.post("/v1/modules/M22-01/verify", content=b"[")
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert (
        client.post("/v1/modules/M22-01/verify", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    assert "Traceback" not in malformed.text


def test_fastapi_pending_adjudication_returns_explicit_abstention() -> None:
    request = _request()
    pending = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.REVIEWED})
    payload = request.model_dump(mode="python")
    payload["adjudications"] = (pending, *request.adjudications[1:])
    pending_request = request.__class__(**payload)
    client = TestClient(create_app(M2201Service()))
    response = client.post(
        "/v1/modules/M22-01/curate",
        json=pending_request.model_dump(mode="json"),
    )
    assert response.status_code == _HTTP_OK
    assert response.json()["status"] == "abstained"
    assert response.json()["package"] is None


def test_plugin_is_strict_parse_once_and_requires_token() -> None:
    request = _request()
    plugin = M2201Plugin(M2201Service())
    validated = plugin.validate(ReferenceTruthSubmission(request=request.model_dump_json()))
    result = plugin.run(validated)
    assert plugin.replay(result).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M22-01"
    with pytest.raises(TypeError, match="reference-truth submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_typer_export_curate_verify_and_no_overwrite(tmp_path: Path) -> None:
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
    assert runner.invoke(cli_app, ["curate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_app, ["curate", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_app, ["curate", str(request_path), "--output", str(result_path)]
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
    assert runner.invoke(cli_app, ["curate", str(bad_request)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"[]")
    assert runner.invoke(cli_app, ["verify", str(bad_result)]).exit_code != 0
    result_path = tmp_path / "valid-result.json"
    result_path.write_bytes(canonical_json_bytes(M2201Service().curate(_request())))

    class ReplayFailure:
        def verify_replay(self, _result: object) -> object:
            raise ValueError

    monkeypatch.setattr(cli_module, "_SERVICE", ReplayFailure())
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0

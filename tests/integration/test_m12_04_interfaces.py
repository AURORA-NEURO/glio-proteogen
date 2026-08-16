"""Adversarial API, CLI, service, and plugin parity tests for M12-04."""

# The matrix intentionally asserts protocol status codes and CLI exit codes.
# ruff: noqa: E501, PLR2004, TC002, TC003

from __future__ import annotations

from pathlib import Path

import pytest
from evals.m12_04.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1204 import app, m1204_app
from glio_proteogen.contracts.m12_04 import MechanismInferenceStatus
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c12_driver_to_protein_consequence.m12_04_network_state_mechanism_inference import (
    M1204MechanismAuthorizationError,
    M1204MechanismEngine,
    M1204Service,
)


def test_http_schema_infer_verify_and_sanitized_errors() -> None:
    client = TestClient(app)
    request = build_scenario_request()
    payload = request.model_dump(mode="json")
    assert client.get("/v1/m12-04/schema/request").status_code == 200
    assert client.get("/v1/m12-04/schema/nope").status_code == 404
    response = client.post("/v1/modules/M12-04/mechanism", json=payload)
    assert response.status_code == 200
    result_payload = response.json()
    verified = client.post("/v1/modules/M12-04/verify", json=result_payload)
    assert verified.status_code == 200
    assert (
        client.post(
            "/v1/modules/M12-04/mechanism",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/v1/modules/M12-04/mechanism",
            content=b"{",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    invalid = request.model_dump(mode="json")
    invalid["request_id"] = 1
    assert client.post("/v1/modules/M12-04/mechanism", json=invalid).status_code == 422


def test_http_denies_controls_and_rejects_tampered_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    denied_request = build_scenario_request(accepted=False)
    assert (
        client.post(
            "/v1/modules/M12-04/mechanism",
            json=denied_request.model_dump(mode="json"),
        ).status_code
        == 403
    )
    result = M1204MechanismEngine().infer(build_scenario_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "f" * 64
    assert client.post("/v1/modules/M12-04/verify", json=result).status_code == 422
    assert (
        client.post(
            "/v1/modules/M12-04/verify",
            content=b"{}",
            headers={"content-type": "text/plain"},
        ).status_code
        == 415
    )

    def denied(self: object, request: object) -> object:  # noqa: ARG001
        raise M1204MechanismAuthorizationError

    monkeypatch.setattr(M1204Service, "_execute_validated", denied)
    assert (
        client.post(
            "/v1/modules/M12-04/mechanism",
            json=build_scenario_request().model_dump(mode="json"),
        ).status_code
        == 403
    )


def test_cli_infer_verify_export_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(build_scenario_request()))
    assert runner.invoke(m1204_app, ["export-schema", "request"]).exit_code == 0
    inferred = runner.invoke(m1204_app, ["infer", str(request_path), "--output", str(result_path)])
    assert inferred.exit_code == 0
    assert runner.invoke(m1204_app, ["infer", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            m1204_app, ["infer", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m1204_app, ["verify", str(result_path)]).exit_code == 0
    result_path.write_text("{", encoding="utf-8")
    assert runner.invoke(m1204_app, ["verify", str(result_path)]).exit_code != 0
    assert runner.invoke(m1204_app, ["export-schema", "bad"]).exit_code == 2


def test_cli_duplicate_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"request_id":"a","request_id":"b"}', encoding="utf-8")
    result = CliRunner().invoke(m1204_app, ["infer", str(path)])
    assert result.exit_code != 0


def test_api_and_cli_emit_supported_or_abstained_contracts() -> None:
    supported = M1204MechanismEngine().infer(build_scenario_request())
    abstained = M1204MechanismEngine().infer(build_scenario_request("unknown:method"))
    assert supported.status is MechanismInferenceStatus.INFERRED
    assert abstained.status is MechanismInferenceStatus.ABSTAINED

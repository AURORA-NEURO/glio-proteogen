"""API/CLI parity tests for provisional M10-06."""

# Transport status and exit-code literals are intentional assertions.
# ruff: noqa: PLR2004

import json

from evals.m10_06.run import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1006 import create_m1006_app, m1006_app
from glio_proteogen.contracts.m10_06.canonical import result_payload_digest
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_06_uncertainty_decomposition import (
    M1006UncertaintyDecompositionService,
)


def test_api_schema_validate_and_strict_duplicate_rejection() -> None:
    request = build_request().model_dump(mode="json")
    with TestClient(create_m1006_app()) as client:
        schema = client.get("/v1/m10-06/schema/output")
        valid = client.post("/v1/m10-06/validate", json=request)
        duplicate = client.post(
            "/v1/m10-06/validate", content=b'{"request_id":"a","request_id":"b"}'
        )
    assert schema.status_code == 200
    assert schema.json()["x-glio-contract"]["nominalCoverage"] == 0.9
    assert valid.status_code == 200
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"]["type"] == "json_duplicate_key"


def test_api_decompose_verify_tamper_and_sanitized_errors() -> None:
    request = build_request().model_dump(mode="json")
    with TestClient(create_m1006_app()) as client:
        decomposed = client.post("/v1/m10-06/decompose", json=request)
        verified = client.post("/v1/m10-06/verify", json=decomposed.json())
        tampered = client.post(
            "/v1/m10-06/verify",
            json=dict(decomposed.json(), abstention_reason="tampered"),
        )
        invalid = client.post("/v1/m10-06/validate", json={"request_id": "secret"})
        invalid_decompose = client.post("/v1/m10-06/decompose", json={"request_id": "secret"})
    assert decomposed.status_code == 200
    assert decomposed.json()["status"] == "abstained"
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    assert tampered.status_code == 409
    assert invalid.status_code == 422
    assert invalid_decompose.status_code == 422
    assert "secret" not in invalid.text


def test_api_maps_authorization_and_malformed_json() -> None:
    denied = build_request(accepted_controls=False).model_dump(mode="json")
    with TestClient(create_m1006_app()) as client:
        forbidden = client.post("/v1/m10-06/decompose", json=denied)
        malformed = client.post("/v1/m10-06/decompose", content=b"not-json")
        unknown = client.get("/v1/m10-06/schema/nope")
    assert forbidden.status_code == 403
    assert malformed.status_code == 400
    assert unknown.status_code == 404


def test_api_replay_error_and_cli_verify_error_paths(tmp_path) -> None:
    service = M1006UncertaintyDecompositionService()
    result = service.execute(build_request())
    tampered = result.model_copy(update={"abstention_reason": "tampered"})
    tampered_payload = tampered.model_dump(mode="json")
    tampered_payload["result_digest"] = result_payload_digest(tampered)
    with TestClient(create_m1006_app()) as client:
        rejected = client.post("/v1/m10-06/verify", json=tampered_payload)
    assert rejected.status_code == 409
    result_path = tmp_path / "tampered.json"
    result_path.write_text(json.dumps(tampered_payload), encoding="utf-8")
    cli_result = CliRunner().invoke(m1006_app, ["verify", str(result_path)])
    assert cli_result.exit_code == 1
    assert "verification failed" in cli_result.output


def test_cli_validate_decompose_verify_and_export_schema(tmp_path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    valid = runner.invoke(m1006_app, ["validate", str(request_path)])
    decomposed = runner.invoke(m1006_app, ["decompose", str(request_path)])
    result_path = tmp_path / "result.json"
    result_path.write_text(decomposed.stdout, encoding="utf-8")
    verified = runner.invoke(m1006_app, ["verify", str(result_path)])
    schema = runner.invoke(m1006_app, ["export-schema", "sensitivity-envelope"])
    assert valid.exit_code == 0
    assert decomposed.exit_code == 0
    assert json.loads(decomposed.stdout)["status"] == "abstained"
    assert verified.exit_code == 0
    assert json.loads(schema.stdout)["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_cli_rejects_sensitive_duplicate_and_denied_request(tmp_path) -> None:
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text('{"request_id":"secret","request_id":"other"}', encoding="utf-8")
    duplicate = CliRunner().invoke(m1006_app, ["validate", str(duplicate_path)])
    denied_path = tmp_path / "denied.json"
    denied_path.write_text(
        build_request(accepted_controls=False).model_dump_json(), encoding="utf-8"
    )
    denied = CliRunner().invoke(m1006_app, ["decompose", str(denied_path)])
    assert duplicate.exit_code == 2
    assert "secret" not in duplicate.output
    assert "other" not in duplicate.output
    assert denied.exit_code == 2
    assert "caller controls" in denied.output

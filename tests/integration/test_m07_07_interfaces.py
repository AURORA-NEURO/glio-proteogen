"""HTTP, CLI, and sealed-plugin parity for M07-07."""

# ruff: noqa: PLR2004

from __future__ import annotations

import json

import pytest
from evals.m07_07.fixtures import request
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c07_copy_number_dosage.m07_07_calibration_selective_prediction import (
    M0707Plugin,
    M0707Service,
    cli_app,
    router,
)

pytestmark = pytest.mark.integration


def _payload() -> dict[str, object]:
    return request().model_dump(mode="json")


def test_fastapi_validate_calibrate_verify_and_schema_parity() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    payload = _payload()

    validated = client.post("/modules/m07-07/validate", json=payload)
    assert validated.status_code == 200
    assert validated.json()["valid"] is True
    executed = client.post("/modules/m07-07/calibrate", json=payload)
    assert executed.status_code == 200
    result = executed.json()
    assert result["status"] == "calibrated"
    verified = client.post("/modules/m07-07/verify", json=result)
    assert verified.status_code == 200
    assert verified.json()["valid"] is True
    schemas = client.get("/modules/m07-07/schema")
    assert schemas.status_code == 200
    assert len(schemas.json()) == 8


def test_fastapi_duplicate_json_and_unauthorized_inputs_are_sanitized() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    duplicate = b'{"request_id":"x","request_id":"y"}'
    response = client.post("/modules/m07-07/validate", content=duplicate)
    assert response.status_code == 400
    assert "request_id" not in response.text
    blocked = _payload()
    blocked["context"]["references"]["consent"]["state"] = "withheld"  # type: ignore[index]
    response = client.post("/modules/m07-07/validate", json=blocked)
    assert response.status_code == 403
    invalid = client.post("/modules/m07-07/validate", json={})
    assert invalid.status_code == 422
    invalid_execution = client.post("/modules/m07-07/calibrate", json={})
    assert invalid_execution.status_code == 422


def test_fastapi_tampered_result_is_rejected_without_echo() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    result = client.post("/modules/m07-07/calibrate", json=_payload()).json()
    result["result_digest"] = "sha256:" + "f" * 64
    response = client.post("/modules/m07-07/verify", json=result)
    assert response.status_code == 422
    assert "sha256:" + "f" * 64 not in response.text


def test_typer_validate_schema_calibrate_and_no_overwrite(tmp_path) -> None:
    runner = CliRunner()
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")
    valid = runner.invoke(cli_app, ["validate", "--input", str(input_path)])
    assert valid.exit_code == 0
    assert json.loads(valid.stdout)["valid"] is True
    schema_path = tmp_path / "schema.json"
    schema = runner.invoke(cli_app, ["export-schema", "--output", str(schema_path)])
    assert schema.exit_code == 0
    assert len(json.loads(schema_path.read_text(encoding="utf-8"))) == 8
    duplicate_schema = runner.invoke(cli_app, ["export-schema", "--output", str(schema_path)])
    assert duplicate_schema.exit_code != 0
    output_path = tmp_path / "result.json"
    executed = runner.invoke(
        cli_app, ["calibrate", "--input", str(input_path), "--output", str(output_path)]
    )
    assert executed.exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "calibrated"
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{}", encoding="utf-8")
    invalid = runner.invoke(cli_app, ["validate", "--input", str(invalid_path)])
    assert invalid.exit_code != 0
    invalid_execution = runner.invoke(cli_app, ["calibrate", "--input", str(invalid_path)])
    assert invalid_execution.exit_code != 0


def test_plugin_requires_sealed_token_and_matches_service() -> None:
    service = M0707Service()
    plugin = M0707Plugin(service)
    token = plugin.validate(_payload())
    result = plugin.run(token)
    assert result == service.execute(request())
    assert plugin.verify(result, request()).result_digest == result.result_digest
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token.__class__(request=token.request, _seal=object()))

"""FastAPI, Typer and plugin parity for M24-07."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.status import HTTP_200_OK, HTTP_404_NOT_FOUND, HTTP_422_UNPROCESSABLE_ENTITY
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material import (
    m24_07_human_factors_operational_evaluator as m2407,
)
from tests.contract.test_m24_07_hardening import request as request_payload

_SCHEMA_COUNT = 7


def request_bytes() -> bytes:
    return json.dumps(request_payload(), sort_keys=True).encode()


def test_fastapi_schema_validate_evaluate_and_verify_parity() -> None:
    client = TestClient(m2407.create_app())
    schemas = client.get("/v1/modules/M24-07/schemas")
    assert schemas.status_code == HTTP_200_OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    body = request_bytes()
    validated = client.post("/v1/modules/M24-07/validate", content=body)
    assert validated.status_code == HTTP_200_OK
    evaluated = client.post("/v1/modules/M24-07/evaluate", content=body)
    assert evaluated.status_code == HTTP_200_OK
    result = evaluated.json()
    verified = client.post("/v1/modules/M24-07/verify", json={"result": result})
    assert verified.status_code == HTTP_200_OK
    assert verified.json()["verified"] is True


def test_fastapi_sanitizes_unknown_and_invalid_replay_requests() -> None:
    client = TestClient(m2407.create_app())
    invalid = client.post("/v1/modules/M24-07/validate", content=b"[]")
    assert invalid.status_code == HTTP_422_UNPROCESSABLE_ENTITY
    assert "traceback" not in invalid.text.lower()
    missing = client.get("/v1/modules/M24-07/schemas/nope")
    assert missing.status_code == HTTP_404_NOT_FOUND
    replay = client.post("/v1/modules/M24-07/verify", json={"result": {"forged": True}})
    assert replay.status_code == HTTP_422_UNPROCESSABLE_ENTITY


def test_typer_commands_validate_evaluate_verify_and_no_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    output = tmp_path / "result.json"
    path.write_bytes(request_bytes())
    runner = CliRunner()
    validated = runner.invoke(m2407.cli_app, ["validate", str(path)])
    assert validated.exit_code == 0
    evaluated = runner.invoke(m2407.cli_app, ["evaluate", str(path), "--output", str(output)])
    assert evaluated.exit_code == 0
    verified = runner.invoke(m2407.cli_app, ["verify", str(output)])
    assert verified.exit_code == 0
    duplicate = runner.invoke(m2407.cli_app, ["evaluate", str(path), "--output", str(output)])
    assert duplicate.exit_code != 0
    schema = runner.invoke(m2407.cli_app, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert "M24-07" in schema.stdout


def test_plugin_rejects_raw_execution_and_requires_submission_wrapper() -> None:
    service = m2407.M2407Service()
    plugin = m2407.M2407Plugin(service)
    with pytest.raises(TypeError, match="submission"):
        plugin.validate(request_bytes())
    token = plugin.validate(m2407.HumanFactorsSubmission(request_bytes()))
    result = plugin.run(token)
    assert plugin.replay(result).result_digest == result.result_digest

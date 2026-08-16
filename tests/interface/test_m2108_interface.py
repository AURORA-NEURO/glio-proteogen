"""FastAPI, Typer and strict-plugin parity tests for M21-08."""

# ruff: noqa: PLR2004

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - used in annotations by the test runner.

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material.m21_08_evidence_gate_release_adjudicator import (
    M2108Service,
    cli_app,
    create_app,
)
from tests.adversarial.test_m2108_adversarial import _request


def test_fastapi_schema_validate_adjudicate_and_verify_routes() -> None:
    client = TestClient(create_app(M2108Service()))
    schema_response = client.get("/v1/modules/M21-08/schemas")
    assert schema_response.status_code == 200
    assert set(schema_response.json()) == {
        "request",
        "output",
        "requirement",
        "benchmark",
        "risk",
        "approval",
        "release-record",
        "configuration",
        "finding",
    }
    payload = _request().model_dump(mode="json")
    validated = client.post("/v1/modules/M21-08/validate", json=payload)
    assert validated.status_code == 200
    adjudicated = client.post("/v1/modules/M21-08/adjudicate", json=payload)
    assert adjudicated.status_code == 200
    result = adjudicated.json()
    verified = client.post("/v1/modules/M21-08/verify", json={"result": result})
    assert verified.status_code == 200
    assert verified.json()["verified"] is True


def test_fastapi_sanitizes_invalid_input_and_unknown_schema() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/modules/M21-08/schemas/nope").status_code == 404
    response = client.post("/v1/modules/M21-08/adjudicate", content=b'{"bad":true}')
    assert response.status_code == 422
    assert "traceback" not in response.text.lower()


def test_typer_export_validate_adjudicate_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    exported = runner.invoke(cli_app, ["export-schema", "request"])
    assert exported.exit_code == 0
    assert json.loads(exported.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M21-08"
    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    adjudicated = runner.invoke(
        cli_app, ["adjudicate", str(request_path), "--output", str(result_path)]
    )
    assert adjudicated.exit_code == 0
    overwrite = runner.invoke(
        cli_app, ["adjudicate", str(request_path), "--output", str(result_path)]
    )
    assert overwrite.exit_code != 0
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0

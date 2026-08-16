"""FastAPI, Typer and strict plugin interface parity for M22-06."""

# ruff: noqa: INP001, PLR2004

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - used in temporary path annotations.

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material.m22_06_robustness_shift_ood_challenge import (
    M2206Service,
    cli_app,
    create_app,
)
from tests.adversarial.test_m2206_contract_adversarial import _request


def test_fastapi_schema_validate_challenge_and_verify() -> None:
    client = TestClient(create_app(M2206Service()))
    schemas = client.get("/v1/modules/M22-06/schemas")
    assert schemas.status_code == 200
    assert set(schemas.json()) == {
        "request",
        "output",
        "surface",
        "scenario",
        "observation",
        "safe-failure",
        "configuration",
        "finding",
    }
    payload = _request().model_dump(mode="json")
    assert client.post("/v1/modules/M22-06/validate", json=payload).status_code == 200
    challenged = client.post("/v1/modules/M22-06/challenge", json=payload)
    assert challenged.status_code == 200
    verified = client.post("/v1/modules/M22-06/verify", json={"result": challenged.json()})
    assert verified.status_code == 200
    assert verified.json()["verified"] is True


def test_fastapi_sanitizes_invalid_json_and_unknown_schema() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/modules/M22-06/schemas/nope").status_code == 404
    assert client.post("/v1/modules/M22-06/verify", content=b"{").status_code == 422
    assert (
        "traceback"
        not in client.post("/v1/modules/M22-06/challenge", content=b'{"bad":true}').text.lower()
    )


def test_typer_commands_validate_challenge_verify_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    exported = runner.invoke(cli_app, ["export-schema", "request"])
    assert exported.exit_code == 0
    assert json.loads(exported.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M22-06"
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code == 0
    challenged = runner.invoke(
        cli_app, ["challenge", str(request_path), "--output", str(result_path)]
    )
    assert challenged.exit_code == 0
    assert (
        runner.invoke(
            cli_app, ["challenge", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code == 0

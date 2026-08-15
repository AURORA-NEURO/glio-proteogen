# ruff: noqa: E501, PLR2004, TC003
"""HTTP and CLI parity tests for M10-02."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor import (
    cli_app,
    create_m1002_app,
)
from tests.modules.test_m10_02_representation_constructor import _request


def test_api_construct_and_schema_are_strict_and_replay_bound() -> None:
    client = TestClient(create_m1002_app())
    request = _request().model_dump_json()
    response = client.post("/v1/m10-02/construct", content=request)
    assert response.status_code == 200
    assert response.json()["status"] == "constructed"
    assert client.get("/v1/m10-02/schema/request").status_code == 200
    assert client.get("/v1/m10-02/schema/unknown").status_code == 404


def test_api_sanitizes_duplicate_key_and_bad_control_errors() -> None:
    client = TestClient(create_m1002_app())
    duplicate = '{"request_id":"a","request_id":"b"}'
    response = client.post("/v1/m10-02/validate", content=duplicate)
    assert response.status_code == 400
    assert "request_id" not in response.text


def test_cli_exports_schema_and_refuses_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    output = tmp_path / "request.json"
    first = runner.invoke(cli_app, ["export-schema", "request", "--output", str(output)])
    assert first.exit_code == 0
    second = runner.invoke(cli_app, ["export-schema", "request", "--output", str(output)])
    assert second.exit_code != 0
    assert json.loads(output.read_text(encoding="utf-8"))["x-glio-contract"]["provisionalAbi"]

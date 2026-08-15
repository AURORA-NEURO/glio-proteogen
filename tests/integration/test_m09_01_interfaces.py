"""FastAPI, CLI and plugin parity tests for M09-01."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c09_complex_stoichiometry.m09_01_formal_state_feature_schema import (
    api as m0901_api,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_01_formal_state_feature_schema import (
    cli as m0901_cli,
)
from tests.modules.c09_complex_stoichiometry.test_m09_01_formal_state import _request

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_CONTENT = 422


def test_api_validate_execute_and_verify_are_canonical() -> None:
    payload = _request().model_dump(mode="json")
    with TestClient(m0901_api.create_app()) as client:
        validated = client.post("/v1/modules/M09-01/validate", json=payload)
        executed = client.post("/v1/modules/M09-01/execute", json=payload)

        assert validated.status_code == HTTP_OK
        assert executed.status_code == HTTP_OK
        body = executed.json()
        verified = client.post(
            "/v1/modules/M09-01/verify",
            json={"result": body["result"], "canonical": body["canonical"]},
        )
        assert verified.status_code == HTTP_OK
        assert verified.json()["verified"] is True


def test_api_sanitizes_duplicate_json_and_unknown_schema() -> None:
    with TestClient(m0901_api.create_app()) as client:
        duplicate = client.post(
            "/v1/modules/M09-01/validate",
            content=b'{"request_id":"one","request_id":"two"}',
            headers={"content-type": "application/json"},
        )
        unknown = client.get("/v1/modules/M09-01/schemas/not-a-contract")

    assert duplicate.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert unknown.status_code == HTTP_NOT_FOUND


def test_cli_validate_and_execute_no_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()

    validated = runner.invoke(m0901_cli.app, ["validate", str(request_path)])
    executed = runner.invoke(
        m0901_cli.app,
        ["execute", str(request_path), "--output", str(output_path)],
    )
    repeated = runner.invoke(
        m0901_cli.app,
        ["execute", str(request_path), "--output", str(output_path)],
    )

    assert validated.exit_code == 0
    assert executed.exit_code == 0
    assert output_path.exists()
    assert repeated.exit_code != 0

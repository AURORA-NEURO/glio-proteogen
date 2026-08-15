"""HTTP and CLI interface tests for M16-06."""

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app
from tests.runtime.test_m16_06_queue import _request


def test_m1606_http_schema_and_adjudication(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(tmp_path / "m1606-api.sqlite3")) as client:
        schema = client.get("/v1/contracts/M16-06/request/schema")
        assert schema.status_code == 200
        assert schema.json()["x-glio-contract"]["dossierSlice"].endswith("5656-5696")
        response = client.post(
            "/v1/modules/M16-06/reviewer-discrepancy-adjudication",
            json=_request().model_dump(mode="json"),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "recorded"
        assert response.json()["record"]["locked"] is True


def test_m1606_cli_schema_and_adjudication(tmp_path) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    schema = runner.invoke(app, ["reviewer-discrepancy", "export-schema", "request"])
    assert schema.exit_code == 0
    assert "GLIO-PROTEOGEN-M16-06" in schema.stdout
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(_request().model_dump(mode="json")),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["reviewer-discrepancy", "adjudicate", str(request_path)],
    )
    assert result.exit_code == 0
    assert '"status":"recorded"' in result.stdout


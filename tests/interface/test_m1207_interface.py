"""FastAPI and Typer parity tests for provisional M12-07."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - used by Typer's filesystem fixture.

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1207 import app, m1207_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from tests.runtime.test_m1207_runtime import _context, _request

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403


def test_fastapi_adjudicate_and_verify_are_canonical() -> None:
    client = TestClient(app)
    request = _request()
    request_document = request.model_dump(mode="json")
    adjudicated = client.post("/v1/modules/M12-07/adjudicate", json=request_document)
    assert adjudicated.status_code == _HTTP_OK
    result_document = adjudicated.json()
    verified = client.post(
        "/v1/modules/M12-07/verify",
        json={"request": request_document, "result": result_document},
    )
    assert verified.status_code == _HTTP_OK
    assert verified.json() == result_document


def test_fastapi_schema_and_sanitized_auth_error() -> None:
    client = TestClient(app)
    schema = client.get("/v1/m12-07/schema/output")
    assert schema.status_code == _HTTP_OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    denied = _request(context=_context(denied_role="quality"))
    response = client.post(
        "/v1/modules/M12-07/adjudicate",
        json=denied.model_dump(mode="json"),
    )
    assert response.status_code == _HTTP_FORBIDDEN
    assert response.json() == {"detail": "M12-07 upstream authorization denied"}


def test_typer_adjudicate_and_no_overwrite_schema(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request().model_dump(mode="json")))
    result = runner.invoke(m1207_app, ["adjudicate", str(request_path)])
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert parsed["output_type"] == "biomarker_panel_plausibility_adjudication"
    schema_path = tmp_path / "schema.json"
    first = runner.invoke(
        m1207_app,
        ["export-schema", "output", "--output", str(schema_path)],
    )
    assert first.exit_code == 0, first.stdout
    second = runner.invoke(
        m1207_app,
        ["export-schema", "output", "--output", str(schema_path)],
    )
    assert second.exit_code != 0

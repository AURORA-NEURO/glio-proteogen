"""FastAPI and Typer parity tests for provisional M12-07."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - used by Typer's filesystem fixture.

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1207 import app, m1207_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c12_driver_protein_consequence.m12_07_plausibility_adjudicator import (
    M1207PlausibilityAdjudicatorEngine,
)
from tests.runtime.test_m1207_runtime import _context, _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
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


def test_fastapi_rejects_unknown_schema_and_invalid_body() -> None:
    client = TestClient(app)
    assert client.get("/v1/m12-07/schema/unknown").status_code == _HTTP_NOT_FOUND
    response = client.post("/v1/modules/M12-07/adjudicate", json={})
    assert response.status_code == _HTTP_FORBIDDEN


def test_typer_schema_stdout_and_verify_parity(tmp_path: Path) -> None:
    runner = CliRunner()
    schema = runner.invoke(m1207_app, ["export-schema", "output"])
    assert schema.exit_code == 0
    assert '"$schema"' in schema.stdout
    request = _request()
    result = M1207PlausibilityAdjudicatorEngine().adjudicate(request)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(request.model_dump(mode="json")))
    result_path.write_bytes(canonical_json_bytes(result.model_dump(mode="json")))
    verified = runner.invoke(
        m1207_app,
        ["verify", str(request_path), str(result_path)],
    )
    assert verified.exit_code == 0, verified.stdout


def test_typer_sanitizes_rejected_request_and_bad_result(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request().model_dump(mode="json")))
    denied_path = tmp_path / "denied.json"
    denied_path.write_bytes(
        canonical_json_bytes(
            _request(context=_context(denied_role="quality")).model_dump(mode="json")
        )
    )
    denied = runner.invoke(m1207_app, ["adjudicate", str(denied_path)])
    assert denied.exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("{}", encoding="utf-8")
    verify = runner.invoke(
        m1207_app,
        ["verify", str(request_path), str(bad_result)],
    )
    assert verify.exit_code != 0
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    malformed_verify = runner.invoke(
        m1207_app,
        ["verify", str(request_path), str(malformed)],
    )
    assert malformed_verify.exit_code != 0
    missing = runner.invoke(m1207_app, ["adjudicate", str(tmp_path / "missing.json")])
    assert missing.exit_code != 0


def test_typer_sanitizes_unknown_schema_and_write_error(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m1207_app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
    parent_file = tmp_path / "parent-file"
    parent_file.write_text("not a directory", encoding="utf-8")
    write_error = runner.invoke(
        m1207_app,
        ["export-schema", "output", "--output", str(parent_file / "schema.json")],
    )
    assert write_error.exit_code != 0


def test_typer_verify_missing_result_path_uses_sanitized_parameter(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request().model_dump(mode="json")))
    missing = runner.invoke(
        m1207_app,
        ["verify", str(request_path), str(tmp_path / "missing.json")],
    )
    assert missing.exit_code != 0


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

"""FastAPI, Typer, and plugin boundary parity for provisional M20-08."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c20_biomarker_panel.m20_08_translation_monitoring_rollback import (
    M2008TranslationMonitoringEngine,
    cli_app,
    create_app,
)
from tests.contract.test_m20_08_hardening import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE_ENTITY = 422


def test_fastapi_monitor_verify_and_schema_are_canonical() -> None:
    client = TestClient(create_app())
    request = _request()
    document = request.model_dump(mode="json")
    monitored = client.post("/v1/modules/M20-08/monitor", json=document)
    assert monitored.status_code == _HTTP_OK
    result = monitored.json()
    verified = client.post("/v1/modules/M20-08/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    schema = client.get("/v1/modules/M20-08/schemas/output")
    assert schema.status_code == _HTTP_OK
    assert schema.json()["x-glio-contract"]["upstreamInputMediaType"].endswith("m20-07+json")


def test_fastapi_sanitizes_unknown_schema_and_invalid_request() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/modules/M20-08/schemas/unknown").status_code == _HTTP_NOT_FOUND
    response = client.post("/v1/modules/M20-08/monitor", json={})
    assert response.status_code == _HTTP_UNPROCESSABLE_ENTITY
    assert response.json() == {"detail": "request does not satisfy the M20-08 contract"}


def test_typer_monitor_verify_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request.model_dump(mode="json")))
    monitored = runner.invoke(cli_app, ["monitor", str(request_path)])
    assert monitored.exit_code == 0, monitored.stdout
    result_document = json.loads(monitored.stdout)
    result_path = tmp_path / "result.json"
    result_path.write_bytes(canonical_json_bytes(result_document))
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0, verified.stdout
    schema_path = tmp_path / "schema.json"
    first = runner.invoke(cli_app, ["export-schema", "output", "--output", str(schema_path)])
    second = runner.invoke(cli_app, ["export-schema", "output", "--output", str(schema_path)])
    assert first.exit_code == 0
    assert second.exit_code != 0


def test_typer_rejects_bad_result(tmp_path: Path) -> None:
    runner = CliRunner()
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    result = runner.invoke(cli_app, ["verify", str(bad)])
    assert result.exit_code != 0
    assert M2008TranslationMonitoringEngine().infer(_request()).result_digest

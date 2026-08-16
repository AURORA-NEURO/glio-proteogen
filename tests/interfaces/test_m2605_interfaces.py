"""FastAPI, Typer, and strict plugin parity tests for M26-05."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry import (
    M2605Plugin,
    TelemetrySubmission,
    api,
    cli,
)
from tests.runtime.test_m26_05_runtime import _request

if TYPE_CHECKING:
    from pathlib import Path


_SCHEMA_COUNT = 8


def test_api_schema_validate_emit_and_verify_parity() -> None:
    request = _request()
    client = TestClient(api.create_m2605_app())
    schemas = client.get("/v1/modules/M26-05/schemas")
    assert schemas.status_code == HTTPStatus.OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    payload = request.model_dump_json()
    validated = client.post(
        "/v1/modules/M26-05/validate",
        content=payload,
        headers={"content-type": "application/json"},
    )
    emitted = client.post(
        "/v1/modules/M26-05/emit",
        content=payload,
        headers={"content-type": "application/json"},
    )
    assert validated.status_code == HTTPStatus.OK
    assert emitted.status_code == HTTPStatus.OK
    verified = client.post("/v1/modules/M26-05/verify", json=emitted.json())
    assert verified.status_code == HTTPStatus.OK
    assert verified.json()["verified"] is True


def test_api_unknown_schema_duplicate_json_and_bad_replay_are_sanitized() -> None:
    client = TestClient(api.create_m2605_app())
    unknown = client.get("/v1/modules/M26-05/schemas/unknown")
    duplicate = client.post(
        "/v1/modules/M26-05/validate",
        content=b'{"request_id":"first","request_id":"secret"}',
        headers={"content-type": "application/json"},
    )
    malformed = client.post(
        "/v1/modules/M26-05/verify",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert unknown.status_code == HTTPStatus.NOT_FOUND
    assert duplicate.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "secret" not in duplicate.text
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_api_authentication_failure_is_forbidden() -> None:
    request = _request()
    quality = request.context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(update={"quality": quality})
                }
            )
        }
    )
    response = TestClient(api.create_m2605_app()).post(
        "/v1/modules/M26-05/emit", content=denied.model_dump_json()
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "quality" not in response.text


def test_plugin_parse_once_and_canonical_result_parity() -> None:
    request = _request()
    plugin = M2605Plugin()
    token = plugin.validate(TelemetrySubmission(request.model_dump_json()))
    result = plugin.run(token)
    replay = plugin.replay(result)
    assert replay == result
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        plugin.validate(request)  # type: ignore[arg-type]


def test_cli_schema_emit_verify_and_no_overwrite(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    schema_path = tmp_path / "schema.json"
    exported = runner.invoke(cli.app, ["export-schema", "request", "--output", str(schema_path)])
    emitted = runner.invoke(cli.app, ["emit", str(request_path), "--output", str(result_path)])
    verified = runner.invoke(cli.app, ["verify", str(result_path)])
    overwrite = runner.invoke(cli.app, ["export-schema", "request", "--output", str(schema_path)])
    assert exported.exit_code == 0
    assert emitted.exit_code == 0
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True
    assert overwrite.exit_code != 0


def test_cli_unknown_and_duplicate_input_are_sanitized(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(cli.app, ["export-schema", "unknown"])
    bad = tmp_path / "bad.json"
    bad.write_text('{"request_id":"safe","request_id":"secret"}', encoding="utf-8")
    invalid = runner.invoke(cli.app, ["validate", str(bad)])
    assert unknown.exit_code != 0
    assert "unknown M26-05 contract" in unknown.output
    assert invalid.exit_code != 0
    assert "secret" not in invalid.output

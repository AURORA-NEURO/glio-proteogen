"""FastAPI, Typer, and plugin parity tests for provisional M10-01."""

import json
from dataclasses import replace
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema import (
    M1001Plugin,
    M1001Service,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema.api import (
    create_app,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema.cli import (
    app as cli_app,
)
from tests.modules.c10_pathway_proteotype.test_m10_01_formal_state import _request


def test_api_validate_execute_and_schema_are_strict() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    with TestClient(create_app(M1001Service())) as client:
        schema = client.get("/v1/modules/M10-01/schemas/verification")
        validated = client.post("/v1/modules/M10-01/validate", json=payload)
        executed = client.post("/v1/modules/M10-01/execute", json=payload)
        unknown = client.get("/v1/modules/M10-01/schemas/not-a-contract")

    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert validated.status_code == HTTPStatus.OK
    assert executed.status_code == HTTPStatus.OK
    assert executed.json()["result"]["status"] == "valid"
    assert unknown.status_code == HTTPStatus.NOT_FOUND


def test_api_rejects_duplicate_json_keys_without_leaking_details() -> None:
    request = _request()
    body = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    with TestClient(create_app(M1001Service())) as client:
        response = client.post(
            "/v1/modules/M10-01/validate",
            content=body[:-1] + ',"request_id":"forged"}',
        )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "traceback" not in response.text.casefold()


def test_cli_and_plugin_share_canonical_result(tmp_path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(
        json.dumps(request.model_dump(mode="json"), separators=(",", ":")),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli_app,
        ["execute", str(request_path), "--output", str(output_path)],
    )
    plugin = M1001Plugin(M1001Service())
    plugin_result = plugin.run(plugin.validate(request))

    assert result.exit_code == 0, result.stdout
    assert json.loads(output_path.read_text(encoding="utf-8")) == json.loads(
        plugin_result.canonical_bytes
    )


def test_plugin_rejects_unissued_token() -> None:
    request = _request()
    plugin = M1001Plugin(M1001Service())
    token = plugin.validate(request)
    forged = replace(token, _seal=object())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)

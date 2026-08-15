"""API, CLI, and plugin parity checks for provisional M08-05."""

# The long module import paths make the test's ownership explicit.
# ruff: noqa: E501

import json
from http import HTTPStatus

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c08_transcript_protein_discordance.m08_05_mechanism_constraint_integrator import (
    M0805Plugin,
    M0805Service,
    create_app,
)
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_05_mechanism_constraint_integrator.cli import (
    app as cli_app,
)
from tests.modules.c08_transcript_protein_discordance.test_m08_05_integrator import (
    _request,
)


def test_api_validate_integrate_and_schema_are_strict() -> None:
    request = _request("conservation_hold")
    payload = request.model_dump(mode="json")
    with TestClient(create_app(M0805Service())) as client:
        schema = client.get("/v1/modules/M08-05/schemas/verification")
        validated = client.post("/v1/modules/M08-05/validate", json=payload)
        integrated = client.post("/v1/modules/M08-05/integrate", json=payload)
        unknown = client.get("/v1/modules/M08-05/schemas/not-a-contract")

    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert validated.status_code == HTTPStatus.OK
    assert integrated.status_code == HTTPStatus.OK
    assert integrated.json()["result"]["status"] == "estimated"
    assert unknown.status_code == HTTPStatus.NOT_FOUND


def test_api_rejects_duplicate_json_keys_without_leaking_details() -> None:
    request = _request("conservation_hold")
    body = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    with TestClient(create_app(M0805Service())) as client:
        response = client.post(
            "/v1/modules/M08-05/validate",
            content=body[:-1] + ',"request_id":"forged"}',
        )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "traceback" not in response.text.casefold()


def test_cli_and_plugin_use_the_same_canonical_result(tmp_path) -> None:
    request = _request("conservation_hold")
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(
        json.dumps(request.model_dump(mode="json"), separators=(",", ":")),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli_app,
        ["integrate", str(request_path), "--output", str(output_path)],
    )
    plugin = M0805Plugin(M0805Service())
    token = plugin.validate(request)
    plugin_result = plugin.run(token)

    assert result.exit_code == 0, result.stdout
    assert json.loads(output_path.read_text(encoding="utf-8")) == json.loads(
        plugin_result.canonical_bytes
    )

"""API, CLI, and plugin parity checks for provisional M09-08."""

# The long import paths encode module ownership in this focused test.
# ruff: noqa: E501

import json
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c09_complex_stoichiometry.m09_08_evidence_explanation_publisher import (
    M0908Plugin,
    M0908Service,
    ValidatedM0908Request,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_08_evidence_explanation_publisher.api import (
    create_app,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_08_evidence_explanation_publisher.cli import (
    app as cli_app,
)
from tests.modules.c09_complex_stoichiometry.test_m09_08_publisher import _request


def test_api_validate_publish_and_schema_are_strict() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    with TestClient(create_app(M0908Service())) as client:
        schema = client.get("/v1/modules/M09-08/schemas/verification")
        validated = client.post("/v1/modules/M09-08/validate", json=payload)
        published = client.post("/v1/modules/M09-08/publish", json=payload)
        unknown = client.get("/v1/modules/M09-08/schemas/unknown")

    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert validated.status_code == HTTPStatus.OK
    assert published.status_code == HTTPStatus.OK
    assert published.json()["result"]["status"] == "published"
    assert unknown.status_code == HTTPStatus.NOT_FOUND


def test_api_rejects_duplicate_json_keys_without_leaking_details() -> None:
    request = _request()
    body = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    with TestClient(create_app(M0908Service())) as client:
        response = client.post(
            "/v1/modules/M09-08/validate",
            content=body[:-1] + ',"request_id":"forged"}',
        )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "traceback" not in response.text.casefold()


def test_cli_and_plugin_emit_the_same_canonical_result(tmp_path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(
        json.dumps(request.model_dump(mode="json"), separators=(",", ":")),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli_app,
        ["publish", str(request_path), "--output", str(output_path)],
    )
    plugin = M0908Plugin(M0908Service())
    token = plugin.validate(request)
    plugin_result = plugin.run(token)

    assert result.exit_code == 0, result.stdout
    assert json.loads(output_path.read_text(encoding="utf-8")) == json.loads(
        plugin_result.canonical_bytes
    )


def test_plugin_rejects_forged_execution_token() -> None:
    request = _request()
    plugin = M0908Plugin(M0908Service())
    with pytest.raises(TypeError):
        plugin.run(ValidatedM0908Request(request=request, _seal=object()))

"""FastAPI and CLI parity checks for M08-06."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c08_transcript_protein_discordance.m08_06_uncertainty_decomposition.api import (  # noqa: E501
    create_app,
)
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_06_uncertainty_decomposition.cli import (  # noqa: E501
    app as cli_app,
)
from tests.modules.c08_transcript_protein_discordance.test_m08_06_uncertainty import _request

_OK = 200
_NOT_FOUND = 404
_UNPROCESSABLE = 422


def test_api_schema_validate_decompose_verify_parity() -> None:
    request = _request().model_dump(mode="json")
    with TestClient(create_app()) as client:
        schema = client.get("/v1/modules/M08-06/schemas/output")
        assert schema.status_code == _OK
        validated = client.post("/v1/modules/M08-06/validate", json=request)
        assert validated.status_code == _OK
        response = client.post("/v1/modules/M08-06/decompose", json=request)
        assert response.status_code == _OK
        result = response.json()["result"]
        verified = client.post("/v1/modules/M08-06/verify", json=result)
        assert verified.status_code == _OK
        assert verified.json()["verified"] is True


def test_api_rejects_non_strict_json_and_unknown_schema() -> None:
    with TestClient(create_app()) as client:
        unknown = client.get("/v1/modules/M08-06/schemas/nope")
        assert unknown.status_code == _NOT_FOUND
        invalid = client.post(
            "/v1/modules/M08-06/validate",
            content=b'{"request_id":1}',
            headers={"content-type": "application/json"},
        )
        assert invalid.status_code == _UNPROCESSABLE


def test_cli_exports_schema_and_validate_canonical_request(tmp_path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    schema = runner.invoke(cli_app, ["export-schema", "output"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["provisionalAbi"] is True
    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["operation"] == "decompose_transcript_protein_uncertainty"

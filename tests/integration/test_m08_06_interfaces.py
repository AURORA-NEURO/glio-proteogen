"""FastAPI and CLI parity checks for M08-06."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m08_06 import result_payload_digest
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
_FORBIDDEN = 403
_CONFLICT = 409


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


def test_api_maps_validation_authorization_and_replay_errors() -> None:
    request = _request()
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={
                            "consent": request.context.references.consent.model_copy(
                                update={"state": "withheld"}
                            )
                        }
                    )
                }
            )
        }
    )
    with TestClient(create_app()) as client:
        assert (
            client.post("/v1/modules/M08-06/validate", json={"request_id": 1}).status_code
            == _UNPROCESSABLE
        )
        assert (
            client.post(
                "/v1/modules/M08-06/validate", json=denied.model_dump(mode="json")
            ).status_code
            == _FORBIDDEN
        )
        assert (
            client.post(
                "/v1/modules/M08-06/decompose", json=denied.model_dump(mode="json")
            ).status_code
            == _FORBIDDEN
        )
        assert (
            client.post("/v1/modules/M08-06/decompose", json={"request_id": 1}).status_code
            == _UNPROCESSABLE
        )
        assert (
            client.post("/v1/modules/M08-06/verify", json={"result_id": "nope"}).status_code
            == _UNPROCESSABLE
        )
        result = client.post(
            "/v1/modules/M08-06/decompose", json=request.model_dump(mode="json")
        ).json()["result"]
        result["abstention_reason"] = "tampered"
        result["result_digest"] = result_payload_digest(result)
        assert client.post("/v1/modules/M08-06/verify", json=result).status_code == _CONFLICT
        strict = client.post(
            "/v1/modules/M08-06/validate",
            content=b'{"x":NaN}',
            headers={"content-type": "application/json"},
        )
        assert strict.status_code == _UNPROCESSABLE


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


def test_cli_decompose_verify_no_overwrite_and_bad_inputs(tmp_path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    decomposed = runner.invoke(cli_app, ["decompose", str(request_path)])
    assert decomposed.exit_code == 1
    output = runner.invoke(cli_app, ["decompose", str(request_path), "--output", str(result_path)])
    assert output.exit_code == 1
    assert result_path.exists()
    duplicate = runner.invoke(
        cli_app, ["decompose", str(request_path), "--output", str(result_path)]
    )
    assert duplicate.exit_code != 0
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    bad = tmp_path / "bad.json"
    bad.write_text('{"x": NaN}', encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(bad)]).exit_code != 0
    assert runner.invoke(cli_app, ["verify", str(bad)]).exit_code != 0
    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"request_id": "not-a-request"}', encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(malformed)]).exit_code != 0
    assert runner.invoke(cli_app, ["decompose", str(malformed)]).exit_code != 0
    assert runner.invoke(cli_app, ["verify", str(malformed)]).exit_code != 0


def test_cli_validate_requires_existing_path(tmp_path) -> None:
    runner = CliRunner()
    missing = Path(tmp_path) / "does-not-exist.json"
    assert runner.invoke(cli_app, ["validate", str(missing)]).exit_code != 0

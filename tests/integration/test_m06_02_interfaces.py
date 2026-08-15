"""API, CLI and plugin parity tests for M06-02."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m06_02 import contract_json_schema, contract_json_schemas
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c06_protein_abundance.m06_02_representation_feature_constructor import (
    api as m0602_api,
)
from glio_proteogen.modules.c06_protein_abundance.m06_02_representation_feature_constructor import (
    cli as m0602_cli,
)
from tests.contract.test_m06_02_contract import _request

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_api_and_cli_export_identical_schema_inventory() -> None:
    runner = CliRunner()
    contracts = tuple(contract_json_schemas())
    with TestClient(m0602_api.create_app()) as client:
        for name in contracts:
            api = client.get(f"/v1/modules/M06-02/schemas/{name}")
            cli = runner.invoke(m0602_cli.app, ["export-schema", name])
            assert api.status_code == _HTTP_OK
            assert cli.exit_code == 0
            assert api.json() == json.loads(cli.stdout)
            assert api.json() == contract_json_schema(name)


def test_api_and_cli_validate_identical_canonical_request(tmp_path) -> None:
    request = _request()
    encoded = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(encoded)

    with TestClient(m0602_api.create_app()) as client:
        api = client.post("/v1/modules/M06-02/validate", content=encoded)
    cli = CliRunner().invoke(m0602_cli.app, ["validate", str(request_path)])

    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 0
    assert api.json() == json.loads(cli.stdout)


def test_api_and_cli_reject_duplicate_keys_without_leaking_secret(tmp_path) -> None:
    payload = b'{"request_id":"safe","request_id":"secret"}'
    request_path = tmp_path / "duplicate.json"
    request_path.write_bytes(payload)

    with TestClient(m0602_api.create_app()) as client:
        api = client.post("/v1/modules/M06-02/validate", content=payload)
    cli = CliRunner().invoke(m0602_cli.app, ["validate", str(request_path)])

    assert api.status_code == _HTTP_UNPROCESSABLE
    assert "secret" not in api.text
    assert cli.exit_code != 0
    assert "secret" not in cli.stdout


def test_api_and_cli_construct_identical_canonical_result(tmp_path) -> None:
    request = _request()
    encoded = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(encoded)

    with TestClient(m0602_api.create_app()) as client:
        api = client.post("/v1/modules/M06-02/construct", content=encoded)
    cli = CliRunner().invoke(m0602_cli.app, ["construct", str(request_path)])

    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 0
    api_payload = api.json()
    cli_payload = json.loads(cli.stdout)
    assert api_payload["result"] == cli_payload
    assert json.loads(api_payload["canonical"]) == cli_payload


def test_api_and_cli_sanitize_unknown_contract_and_invalid_request(tmp_path) -> None:
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_bytes(b"{}")
    runner = CliRunner()
    unknown = runner.invoke(m0602_cli.app, ["export-schema", "unknown"])
    invalid = runner.invoke(m0602_cli.app, ["validate", str(invalid_path)])
    with TestClient(m0602_api.create_app()) as client:
        api_unknown = client.get("/v1/modules/M06-02/schemas/unknown")
        api_invalid = client.post("/v1/modules/M06-02/validate", content=b"{}")

    assert unknown.exit_code != 0
    assert invalid.exit_code != 0
    assert api_unknown.status_code == _HTTP_NOT_FOUND
    assert api_invalid.status_code == _HTTP_UNPROCESSABLE


def test_api_denies_withheld_consent_before_construction() -> None:
    request = _request()
    refs = request.context.references
    withheld = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": refs.model_copy(
                        update={
                            "consent": refs.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    with TestClient(m0602_api.create_app()) as client:
        response = client.post(
            "/v1/modules/M06-02/construct",
            content=canonical_json_bytes(withheld.model_dump(mode="json")),
        )
    assert response.status_code == _HTTP_FORBIDDEN
    assert "authorization denied" in response.text

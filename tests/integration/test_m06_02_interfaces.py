"""API, CLI and plugin parity tests for M06-02."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m06_02 import (
    RepresentationObservationState,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c06_protein_abundance.m06_02_representation_feature_constructor import (
    api as m0602_api,
)
from glio_proteogen.modules.c06_protein_abundance.m06_02_representation_feature_constructor import (
    cli as m0602_cli,
)
from glio_proteogen.modules.c06_protein_abundance.m06_02_representation_feature_constructor import (
    engine as m0602_engine,
)
from tests.contract.test_m06_02_contract import _request
from tests.modules.c06_protein_abundance.test_m06_02_representation_constructor import (
    _with_feature_state,
)

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


def test_api_construct_sanitizes_validation_and_input_failures() -> None:
    class FailingService:
        def validate_request(self, request: object) -> object:
            return request

        def construct(self, _request: object) -> object:
            raise m0602_engine.RepresentationInputError("result_bytes")

    with TestClient(m0602_api.create_app(FailingService())) as client:  # type: ignore[arg-type]
        invalid = client.post("/v1/modules/M06-02/construct", content=b"{}")
        rejected = client.post(
            "/v1/modules/M06-02/construct",
            content=canonical_json_bytes(_request().model_dump(mode="json")),
        )
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert rejected.status_code == _HTTP_UNPROCESSABLE
    assert rejected.json()["detail"] == "M06-02 input rejected"


def test_api_validate_denies_withheld_consent() -> None:
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
            "/v1/modules/M06-02/validate",
            content=canonical_json_bytes(withheld.model_dump(mode="json")),
        )
    assert response.status_code == _HTTP_FORBIDDEN


def test_cli_construct_output_overwrite_and_abstention(tmp_path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request().model_dump(mode="json")))
    output = tmp_path / "result.json"
    first = CliRunner().invoke(
        m0602_cli.app,
        ["construct", str(request_path), "--output", str(output)],
    )
    second = CliRunner().invoke(
        m0602_cli.app,
        ["construct", str(request_path), "--output", str(output)],
    )

    unsupported = _with_feature_state(RepresentationObservationState.UNSUPPORTED)
    unsupported_path = tmp_path / "unsupported.json"
    unsupported_path.write_bytes(canonical_json_bytes(unsupported.model_dump(mode="json")))
    abstained = CliRunner().invoke(m0602_cli.app, ["construct", str(unsupported_path)])

    invalid_path = tmp_path / "invalid-construct.json"
    invalid_path.write_bytes(b"{}")
    invalid = CliRunner().invoke(m0602_cli.app, ["construct", str(invalid_path)])
    assert first.exit_code == 0
    assert second.exit_code != 0
    assert output.exists()
    assert abstained.exit_code == 1
    assert invalid.exit_code != 0

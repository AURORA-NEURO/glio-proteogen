"""API, CLI, and plugin parity tests for M06-05."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m06_05 import contract_json_schema, contract_json_schemas
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c06_protein_abundance.m06_05_mechanism_constraint_integrator import (
    ConstraintIntegrationSubmission,
    M0605Plugin,
    ValidatedM0605Request,
)
from glio_proteogen.modules.c06_protein_abundance.m06_05_mechanism_constraint_integrator import (
    api as m0605_api,
)
from glio_proteogen.modules.c06_protein_abundance.m06_05_mechanism_constraint_integrator import (
    cli as m0605_cli,
)
from tests.modules.c06_protein_abundance.test_m06_05_constraint_integrator import _request

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_api_and_cli_export_identical_schema_inventory() -> None:
    runner = CliRunner()
    with TestClient(m0605_api.create_app()) as client:
        for name in contract_json_schemas():
            api = client.get(f"/v1/modules/M06-05/schemas/{name}")
            cli = runner.invoke(m0605_cli.app, ["export-schema", name])
            assert api.status_code == _HTTP_OK
            assert cli.exit_code == 0
            assert api.json() == json.loads(cli.stdout)
            assert api.json() == contract_json_schema(name)


def test_api_and_cli_validate_identical_request(tmp_path) -> None:
    encoded = canonical_json_bytes(_request().model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(encoded)
    with TestClient(m0605_api.create_app()) as client:
        api = client.post("/v1/modules/M06-05/validate", content=encoded)
    cli = CliRunner().invoke(m0605_cli.app, ["validate", str(request_path)])
    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 0
    assert api.json() == json.loads(cli.stdout)


def test_api_and_cli_integrate_identical_canonical_result(tmp_path) -> None:
    encoded = canonical_json_bytes(_request().model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(encoded)
    with TestClient(m0605_api.create_app()) as client:
        api = client.post("/v1/modules/M06-05/integrate", content=encoded)
    cli = CliRunner().invoke(m0605_cli.app, ["integrate", str(request_path)])
    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 0
    assert api.json()["result"] == json.loads(cli.stdout)
    assert json.loads(api.json()["canonical"]) == json.loads(cli.stdout)


def test_plugin_parse_once_requires_validated_token() -> None:
    request = _request()
    plugin = M0605Plugin()
    submission = ConstraintIntegrationSubmission(
        canonical_json_bytes(request.model_dump(mode="json"))
    )
    validated = plugin.validate(submission)
    assert isinstance(validated, ValidatedM0605Request)
    assert plugin.run(validated).result.status.value == "integrated"
    assert plugin.validate_request(request) == request
    assert plugin.validate(ConstraintIntegrationSubmission(request)).request == request


def test_plugin_rejects_unvalidated_token_and_bad_submission() -> None:
    plugin = M0605Plugin()
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="constraint integration submission"):
        plugin.validate(object())


def test_duplicate_json_keys_are_rejected_without_secret_leak(tmp_path) -> None:
    payload = b'{"request_id":"safe","request_id":"secret"}'
    request_path = tmp_path / "duplicate.json"
    request_path.write_bytes(payload)
    with TestClient(m0605_api.create_app()) as client:
        api = client.post("/v1/modules/M06-05/validate", content=payload)
    cli = CliRunner().invoke(m0605_cli.app, ["validate", str(request_path)])
    assert api.status_code == _HTTP_UNPROCESSABLE
    assert "secret" not in api.text
    assert cli.exit_code != 0
    assert "secret" not in cli.stdout


def test_unknown_schema_and_invalid_request_are_sanitized(tmp_path) -> None:
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_bytes(b"{}")
    runner = CliRunner()
    unknown = runner.invoke(m0605_cli.app, ["export-schema", "unknown"])
    invalid = runner.invoke(m0605_cli.app, ["validate", str(invalid_path)])
    with TestClient(m0605_api.create_app()) as client:
        api_unknown = client.get("/v1/modules/M06-05/schemas/unknown")
        api_invalid = client.post("/v1/modules/M06-05/validate", content=b"{}")
    assert unknown.exit_code != 0
    assert invalid.exit_code != 0
    assert api_unknown.status_code == _HTTP_NOT_FOUND
    assert api_invalid.status_code == _HTTP_UNPROCESSABLE


def test_api_denies_withheld_consent_before_integration() -> None:
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
    with TestClient(m0605_api.create_app()) as client:
        response = client.post(
            "/v1/modules/M06-05/integrate",
            content=canonical_json_bytes(withheld.model_dump(mode="json")),
        )
    assert response.status_code == _HTTP_FORBIDDEN
    assert "authorization denied" in response.text


def test_cli_output_is_non_overwriting_and_abstention_exits_one(tmp_path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request().model_dump(mode="json")))
    output = tmp_path / "result.json"
    first = CliRunner().invoke(
        m0605_cli.app, ["integrate", str(request_path), "--output", str(output)]
    )
    second = CliRunner().invoke(
        m0605_cli.app, ["integrate", str(request_path), "--output", str(output)]
    )
    invalid = CliRunner().invoke(m0605_cli.app, ["integrate", str(tmp_path / "missing.json")])
    assert first.exit_code == 0
    assert second.exit_code != 0
    assert output.exists()
    assert invalid.exit_code != 0

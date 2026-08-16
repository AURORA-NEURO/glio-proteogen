"""API, CLI, and plugin parity tests for M07-05."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m07_05 import contract_json_schema, contract_json_schemas
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c07_copy_number_dosage.m07_05_mechanism_constraint_integrator import (
    ConstraintInputError,
    ConstraintSubmission,
    M0705Plugin,
    ValidatedM0705Request,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_05_mechanism_constraint_integrator import (
    api as m0705_api,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_05_mechanism_constraint_integrator import (
    cli as m0705_cli,
)
from tests.modules.c07_copy_number_dosage.test_m07_05_constraint import _request

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_api_and_cli_export_identical_schema_inventory() -> None:
    runner = CliRunner()
    with TestClient(m0705_api.create_app()) as client:
        for name in contract_json_schemas():
            api = client.get(f"/v1/modules/M07-05/schemas/{name}")
            cli = runner.invoke(m0705_cli.app, ["export-schema", name])
            assert api.status_code == _HTTP_OK
            assert cli.exit_code == 0
            assert api.json() == json.loads(cli.stdout)
            assert api.json() == contract_json_schema(name)


def test_api_and_cli_validate_identical_request(tmp_path) -> None:
    encoded = canonical_json_bytes(_request().model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(encoded)
    with TestClient(m0705_api.create_app()) as client:
        api = client.post("/v1/modules/M07-05/validate", content=encoded)
    cli = CliRunner().invoke(m0705_cli.app, ["validate", str(request_path)])
    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 0
    assert api.json() == json.loads(cli.stdout)


def test_api_and_cli_integrate_identical_canonical_result(tmp_path) -> None:
    encoded = canonical_json_bytes(_request().model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(encoded)
    with TestClient(m0705_api.create_app()) as client:
        api = client.post("/v1/modules/M07-05/integrate", content=encoded)
    cli = CliRunner().invoke(m0705_cli.app, ["integrate", str(request_path)])
    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 0
    assert api.json()["result"] == json.loads(cli.stdout)
    assert json.loads(api.json()["canonical"]) == json.loads(cli.stdout)


def test_plugin_parse_once_requires_validated_token() -> None:
    request = _request()
    plugin = M0705Plugin()
    submission = ConstraintSubmission(canonical_json_bytes(request.model_dump(mode="json")))
    validated = plugin.validate(submission)
    assert isinstance(validated, ValidatedM0705Request)
    assert plugin.run(validated).result.status.value == "integrated"
    assert plugin.validate_request(request) == request
    assert plugin.validate(ConstraintSubmission(request)).request == request
    assert plugin.integrate(request).canonical_bytes == plugin.execute(request).canonical_bytes


def test_plugin_rejects_unvalidated_token_and_bad_submission() -> None:
    plugin = M0705Plugin()
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="constraint submission"):
        plugin.validate(object())


def test_duplicate_keys_unknown_schema_and_invalid_request_are_sanitized(tmp_path) -> None:
    payload = b'{"request_id":"safe","request_id":"secret"}'
    request_path = tmp_path / "duplicate.json"
    request_path.write_bytes(payload)
    with TestClient(m0705_api.create_app()) as client:
        duplicate = client.post("/v1/modules/M07-05/validate", content=payload)
        unknown = client.get("/v1/modules/M07-05/schemas/unknown")
        invalid = client.post("/v1/modules/M07-05/validate", content=b"{}")
    cli = CliRunner().invoke(m0705_cli.app, ["validate", str(request_path)])
    assert duplicate.status_code == _HTTP_UNPROCESSABLE
    assert "secret" not in duplicate.text
    assert unknown.status_code == _HTTP_NOT_FOUND
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert cli.exit_code != 0
    assert "secret" not in cli.stdout


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
    with TestClient(m0705_api.create_app()) as client:
        response = client.post(
            "/v1/modules/M07-05/integrate",
            content=canonical_json_bytes(withheld.model_dump(mode="json")),
        )
    assert response.status_code == _HTTP_FORBIDDEN
    assert "authorization denied" in response.text


def test_cli_output_is_non_overwriting_and_api_input_handler_is_sanitized(tmp_path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request().model_dump(mode="json")))
    output = tmp_path / "result.json"
    first = CliRunner().invoke(
        m0705_cli.app, ["integrate", str(request_path), "--output", str(output)]
    )
    second = CliRunner().invoke(
        m0705_cli.app, ["integrate", str(request_path), "--output", str(output)]
    )
    assert first.exit_code == 0
    assert second.exit_code != 0
    assert output.exists()
    with (
        patch.object(
            m0705_api.M0705Service,
            "integrate",
            side_effect=ConstraintInputError("result_digest"),
        ),
        TestClient(m0705_api.create_app()) as client,
    ):
        rejected = client.post(
            "/v1/modules/M07-05/integrate",
            content=canonical_json_bytes(_request().model_dump(mode="json")),
        )
    assert rejected.status_code == _HTTP_UNPROCESSABLE
    assert rejected.json() == {"detail": "M07-05 input rejected"}

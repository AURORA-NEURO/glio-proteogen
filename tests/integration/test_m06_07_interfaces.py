"""API, CLI, and plugin parity tests for M06-07."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m06_07 import contract_json_schema, contract_json_schemas
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c06_protein_abundance.m06_07_calibration_selective_prediction import (
    CalibrationInputError,
    CalibrationSubmission,
    M0607Plugin,
    ValidatedM0607Request,
)
from glio_proteogen.modules.c06_protein_abundance.m06_07_calibration_selective_prediction import (
    api as m0607_api,
)
from glio_proteogen.modules.c06_protein_abundance.m06_07_calibration_selective_prediction import (
    cli as m0607_cli,
)
from tests.modules.c06_protein_abundance.test_m06_07_calibration import _request

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_api_and_cli_export_identical_schema_inventory() -> None:
    runner = CliRunner()
    with TestClient(m0607_api.create_app()) as client:
        for name in contract_json_schemas():
            api = client.get(f"/v1/modules/M06-07/schemas/{name}")
            cli = runner.invoke(m0607_cli.app, ["export-schema", name])
            assert api.status_code == _HTTP_OK
            assert cli.exit_code == 0
            assert api.json() == json.loads(cli.stdout)
            assert api.json() == contract_json_schema(name)


def test_api_and_cli_validate_identical_request(tmp_path) -> None:
    encoded = canonical_json_bytes(_request().model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(encoded)
    with TestClient(m0607_api.create_app()) as client:
        api = client.post("/v1/modules/M06-07/validate", content=encoded)
    cli = CliRunner().invoke(m0607_cli.app, ["validate", str(request_path)])
    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 0
    assert api.json() == json.loads(cli.stdout)


def test_api_and_cli_calibrate_identical_canonical_result(tmp_path) -> None:
    encoded = canonical_json_bytes(_request().model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(encoded)
    with TestClient(m0607_api.create_app()) as client:
        api = client.post("/v1/modules/M06-07/calibrate", content=encoded)
    cli = CliRunner().invoke(m0607_cli.app, ["calibrate", str(request_path)])
    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 0
    assert api.json()["result"] == json.loads(cli.stdout)
    assert json.loads(api.json()["canonical"]) == json.loads(cli.stdout)


def test_plugin_parse_once_requires_validated_token() -> None:
    request = _request()
    plugin = M0607Plugin()
    submission = CalibrationSubmission(canonical_json_bytes(request.model_dump(mode="json")))
    validated = plugin.validate(submission)
    assert isinstance(validated, ValidatedM0607Request)
    assert plugin.run(validated).result.status.value == "calibrated"
    assert plugin.validate_request(request) == request
    assert plugin.validate(CalibrationSubmission(request)).request == request


def test_plugin_rejects_unvalidated_token_and_bad_submission() -> None:
    plugin = M0607Plugin()
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="calibration submission"):
        plugin.validate(object())


def test_duplicate_json_keys_are_rejected_without_secret_leak(tmp_path) -> None:
    payload = b'{"request_id":"safe","request_id":"secret"}'
    request_path = tmp_path / "duplicate.json"
    request_path.write_bytes(payload)
    with TestClient(m0607_api.create_app()) as client:
        api = client.post("/v1/modules/M06-07/validate", content=payload)
    cli = CliRunner().invoke(m0607_cli.app, ["validate", str(request_path)])
    assert api.status_code == _HTTP_UNPROCESSABLE
    assert "secret" not in api.text
    assert cli.exit_code != 0
    assert "secret" not in cli.stdout


def test_unknown_schema_and_invalid_request_are_sanitized(tmp_path) -> None:
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_bytes(b"{}")
    runner = CliRunner()
    unknown = runner.invoke(m0607_cli.app, ["export-schema", "unknown"])
    invalid = runner.invoke(m0607_cli.app, ["validate", str(invalid_path)])
    with TestClient(m0607_api.create_app()) as client:
        api_unknown = client.get("/v1/modules/M06-07/schemas/unknown")
        api_invalid = client.post("/v1/modules/M06-07/validate", content=b"{}")
    assert unknown.exit_code != 0
    assert invalid.exit_code != 0
    assert api_unknown.status_code == _HTTP_NOT_FOUND
    assert api_invalid.status_code == _HTTP_UNPROCESSABLE


def test_api_denies_withheld_consent_before_calibration() -> None:
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
    with TestClient(m0607_api.create_app()) as client:
        response = client.post(
            "/v1/modules/M06-07/calibrate",
            content=canonical_json_bytes(withheld.model_dump(mode="json")),
        )
    assert response.status_code == _HTTP_FORBIDDEN
    assert "authorization denied" in response.text


def test_cli_output_is_non_overwriting_and_abstention_exits_one(tmp_path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request().model_dump(mode="json")))
    output = tmp_path / "result.json"
    first = CliRunner().invoke(
        m0607_cli.app, ["calibrate", str(request_path), "--output", str(output)]
    )
    second = CliRunner().invoke(
        m0607_cli.app, ["calibrate", str(request_path), "--output", str(output)]
    )
    assert first.exit_code == 0
    assert second.exit_code != 0
    assert output.exists()


def test_api_validation_auth_and_calibration_input_handlers() -> None:
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
    encoded = canonical_json_bytes(withheld.model_dump(mode="json"))
    with TestClient(m0607_api.create_app()) as client:
        denied = client.post("/v1/modules/M06-07/validate", content=encoded)
        invalid = client.post("/v1/modules/M06-07/calibrate", content=b"{}")
    assert denied.status_code == _HTTP_FORBIDDEN
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    with patch.object(
        m0607_api.M0607Service,
        "calibrate",
        side_effect=CalibrationInputError("result_digest"),
    ), TestClient(m0607_api.create_app()) as client:
        rejected = client.post(
            "/v1/modules/M06-07/calibrate",
            content=canonical_json_bytes(_request().model_dump(mode="json")),
        )
    assert rejected.status_code == _HTTP_UNPROCESSABLE
    assert rejected.json() == {"detail": "M06-07 input rejected"}


def test_cli_invalid_calibration_and_abstention_paths(tmp_path) -> None:
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_bytes(b"{}")
    invalid = CliRunner().invoke(m0607_cli.app, ["calibrate", str(invalid_path)])
    assert invalid.exit_code != 0
    abstained_path = tmp_path / "abstained.json"
    abstained_path.write_bytes(
        canonical_json_bytes(_request(upstream_decomposed=False).model_dump(mode="json"))
    )
    abstained = CliRunner().invoke(m0607_cli.app, ["calibrate", str(abstained_path)])
    assert abstained.exit_code == 1
    assert json.loads(abstained.stdout)["status"] == "abstained"


def test_plugin_direct_calibrate_and_execute_are_compatible() -> None:
    plugin = M0607Plugin()
    request = _request()
    assert plugin.calibrate(request).canonical_bytes == plugin.execute(request).canonical_bytes

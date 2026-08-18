"""Black-box API/CLI parity and strict boundary tests for M20-01."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import m2001
from glio_proteogen.adapters.api import create_app as create_central_app
from glio_proteogen.adapters.cli import app as central_cli_app
from glio_proteogen.contracts.m20_01 import (
    ProteinSubtypeUpstreamResolutionResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from tests.contract.test_m20_01_adversarial import _request

if TYPE_CHECKING:
    from pathlib import Path

    from glio_proteogen.contracts.m20_01.schema import ContractName

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_UNSUPPORTED_MEDIA_TYPE = 415
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
CLI_USAGE_ERROR = 2


def test_schema_endpoint_and_cli_export_are_identical() -> None:
    name = "request"
    with TestClient(m2001.app) as client:
        response = client.get(f"/v1/m20-01/schema/{name}")
    cli = CliRunner().invoke(m2001.m2001_app, ["export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert (
        response.json()
        == json.loads(cli.stdout)
        == contract_json_schema(cast("ContractName", name))
    )

    with TestClient(m2001.app) as client:
        missing = client.get("/v1/m20-01/schema/not-a-schema")
    bad_cli = CliRunner().invoke(m2001.m2001_app, ["export-schema", "not-a-schema"])
    assert missing.status_code == HTTP_NOT_FOUND
    assert bad_cli.exit_code == CLI_USAGE_ERROR
    assert "unknown M20-01 schema" in bad_cli.output


def test_api_cli_and_library_emit_canonical_result_parity(tmp_path: Path) -> None:
    serialized = canonical_json_bytes(_request().model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(serialized)

    with TestClient(m2001.app) as client:
        api_response = client.post(
            "/v1/modules/M20-01/resolve",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        m2001.m2001_app,
        ["resolve", str(request_path), "--output", str(output_path)],
    )

    assert api_response.status_code == HTTP_OK, api_response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteinSubtypeUpstreamResolutionResult.model_validate_json(
        api_response.content, strict=True
    )
    cli_result = ProteinSubtypeUpstreamResolutionResult.model_validate_json(
        output_path.read_bytes(), strict=True
    )
    assert api_result == cli_result

    with TestClient(m2001.app) as client:
        verify_response = client.post(
            "/v1/modules/M20-01/verify",
            content=output_path.read_bytes(),
            headers={"content-type": "application/json"},
        )
    verify_cli = CliRunner().invoke(m2001.m2001_app, ["verify", str(output_path)])
    assert verify_response.status_code == HTTP_OK
    assert verify_cli.exit_code == 0, verify_cli.output
    assert (
        ProteinSubtypeUpstreamResolutionResult.model_validate_json(
            verify_response.content, strict=True
        )
        == cli_result
    )


def test_interfaces_reject_wrong_media_type_and_control_before_validation(tmp_path: Path) -> None:
    serialized = canonical_json_bytes(_request().model_dump(mode="json"))
    rejected = json.loads(serialized)
    rejected["context"]["references"]["consent"]["state"] = "withheld"
    rejected_bytes = json.dumps(rejected).encode()
    request_path = tmp_path / "rejected.json"
    request_path.write_bytes(rejected_bytes)

    with TestClient(m2001.app) as client:
        wrong_type = client.post(
            "/v1/modules/M20-01/resolve",
            content=serialized,
            headers={"content-type": "text/plain"},
        )
        denied = client.post(
            "/v1/modules/M20-01/resolve",
            content=rejected_bytes,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(m2001.m2001_app, ["resolve", str(request_path)])

    assert wrong_type.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert denied.status_code == HTTP_FORBIDDEN
    assert cli.exit_code == 1
    assert "resolution failed" in cli.output
    assert "Traceback" not in cli.output


def test_interfaces_sanitize_malformed_json_and_tampered_results(tmp_path: Path) -> None:
    with TestClient(m2001.app) as client:
        malformed = client.post(
            "/v1/modules/M20-01/resolve",
            content=b"{not-json",
            headers={"content-type": "application/json"},
        )
        bad_verify = client.post(
            "/v1/modules/M20-01/verify",
            content=b"{}",
            headers={"content-type": "application/json"},
        )
    assert malformed.status_code == HTTP_UNPROCESSABLE
    assert malformed.json() == {"detail": "invalid JSON request"}
    assert bad_verify.status_code == HTTP_UNPROCESSABLE
    assert bad_verify.json() == {"detail": "M20-01 result verification failed"}

    result_path = tmp_path / "tampered-result.json"
    result_path.write_text("{}", encoding="utf-8")
    cli = CliRunner().invoke(m2001.m2001_app, ["verify", str(result_path)])
    assert cli.exit_code == 1
    assert "verification failed: M20-01 result is invalid" in cli.output


def test_cli_refuses_overwrite(tmp_path: Path) -> None:
    serialized = canonical_json_bytes(_request().model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "existing.json"
    request_path.write_bytes(serialized)
    output_path.write_text("existing", encoding="utf-8")

    cli = CliRunner().invoke(
        m2001.m2001_app,
        ["resolve", str(request_path), "--output", str(output_path)],
    )

    assert cli.exit_code != 0
    assert "output already exists" in cli.output
    assert output_path.read_text(encoding="utf-8") == "existing"


def test_central_api_and_cli_register_m2001_surface(tmp_path: Path) -> None:
    request = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(serialized)

    with TestClient(create_central_app(tmp_path / "events.sqlite")) as client:
        schema = client.get("/v1/contracts/M20-01/request/schema")
        resolved = client.post(
            "/v1/modules/M20-01/resolve",
            content=serialized,
            headers={"content-type": "application/json"},
        )
        verified = client.post(
            "/v1/modules/M20-01/verify",
            content=resolved.content,
            headers={"content-type": "application/json"},
        )

    assert schema.status_code == HTTP_OK
    assert schema.json() == contract_json_schema("request")
    assert resolved.status_code == HTTP_OK, resolved.text
    assert verified.status_code == HTTP_OK, verified.text
    assert verified.json() == resolved.json()

    schema_cli = CliRunner().invoke(
        central_cli_app,
        ["m2001-upstream", "export-schema", "request"],
    )
    result_cli = CliRunner().invoke(
        central_cli_app,
        ["m2001-upstream", "resolve", str(request_path), "--output", str(result_path)],
    )
    assert schema_cli.exit_code == 0, schema_cli.output
    assert json.loads(schema_cli.stdout) == contract_json_schema("request")
    assert result_cli.exit_code == 0, result_cli.output
    assert ProteinSubtypeUpstreamResolutionResult.model_validate_json(
        result_path.read_bytes(), strict=True
    ) == ProteinSubtypeUpstreamResolutionResult.model_validate_json(
        resolved.content, strict=True
    )

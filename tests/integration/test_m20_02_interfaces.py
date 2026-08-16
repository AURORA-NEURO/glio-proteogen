"""Black-box API/CLI parity tests for M20-02."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import m2002
from glio_proteogen.contracts.m20_02 import (
    ProteinSubtypeAlignmentResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from tests.modules.c17_metabolomic_lipidomic_integration.test_m20_02_engine import _request

if TYPE_CHECKING:
    from pathlib import Path

    from glio_proteogen.contracts.m20_02.schema import ContractName

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_UNSUPPORTED_MEDIA_TYPE = 415
HTTP_UNPROCESSABLE = 422
CLI_USAGE_ERROR = 2


def test_schema_endpoint_and_cli_export_match() -> None:
    name = "request"
    with TestClient(m2002.app) as client:
        response = client.get(f"/v1/m20-02/schema/{name}")
    cli = CliRunner().invoke(m2002.m2002_app, ["export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert (
        response.json()
        == json.loads(cli.stdout)
        == contract_json_schema(cast("ContractName", name))
    )
    with TestClient(m2002.app) as client:
        missing = client.get("/v1/m20-02/schema/not-a-schema")
    bad_cli = CliRunner().invoke(m2002.m2002_app, ["export-schema", "not-a-schema"])
    assert missing.status_code == HTTP_NOT_FOUND
    assert bad_cli.exit_code == CLI_USAGE_ERROR
    assert "unknown M20-02 schema" in bad_cli.output


def test_api_cli_and_library_emit_canonical_result_parity(tmp_path: Path) -> None:
    serialized = canonical_json_bytes(_request())
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(serialized)

    with TestClient(m2002.app) as client:
        api_response = client.post(
            "/v1/modules/M20-02/reconcile",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        m2002.m2002_app,
        ["reconcile", str(request_path), "--output", str(output_path)],
    )

    assert api_response.status_code == HTTP_OK, api_response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteinSubtypeAlignmentResult.model_validate_json(
        api_response.content, strict=True
    )
    cli_result = ProteinSubtypeAlignmentResult.model_validate_json(
        output_path.read_bytes(), strict=True
    )
    assert api_result == cli_result

    with TestClient(m2002.app) as client:
        verify_response = client.post(
            "/v1/modules/M20-02/verify",
            content=output_path.read_bytes(),
            headers={"content-type": "application/json"},
        )
    verify_cli = CliRunner().invoke(m2002.m2002_app, ["verify", str(output_path)])
    assert verify_response.status_code == HTTP_OK
    assert verify_cli.exit_code == 0, verify_cli.output


def test_interfaces_sanitize_wrong_content_and_tampering(tmp_path: Path) -> None:
    serialized = canonical_json_bytes(_request())
    rejected = json.loads(serialized)
    rejected["context"]["references"]["consent"]["state"] = "withheld"
    rejected_bytes = json.dumps(rejected).encode()
    invalid_fields = json.loads(serialized)
    invalid_fields["observations"] = []
    invalid_fields_bytes = json.dumps(invalid_fields).encode()
    with TestClient(m2002.app) as client:
        wrong_type = client.post(
            "/v1/modules/M20-02/reconcile",
            content=serialized,
            headers={"content-type": "text/plain"},
        )
        malformed = client.post(
            "/v1/modules/M20-02/reconcile",
            content=b"{not-json",
            headers={"content-type": "application/json"},
        )
        bad_verify = client.post(
            "/v1/modules/M20-02/verify",
            content=b"{}",
            headers={"content-type": "application/json"},
        )
        malformed_fields = client.post(
            "/v1/modules/M20-02/reconcile",
            content=invalid_fields_bytes,
            headers={"content-type": "application/json"},
        )
        wrong_verify_type = client.post(
            "/v1/modules/M20-02/verify",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        denied = client.post(
            "/v1/modules/M20-02/reconcile",
            content=rejected_bytes,
            headers={"content-type": "application/json"},
        )
    assert wrong_type.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert malformed.status_code == HTTP_UNPROCESSABLE
    assert malformed.json() == {"detail": "invalid JSON request"}
    assert bad_verify.status_code == HTTP_UNPROCESSABLE
    assert bad_verify.json() == {"detail": "M20-02 result verification failed"}
    assert malformed_fields.status_code == HTTP_UNPROCESSABLE
    assert isinstance(malformed_fields.json()["detail"], list)
    assert wrong_verify_type.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert denied.status_code == HTTP_FORBIDDEN

    request_path = tmp_path / "request.json"
    output_path = tmp_path / "existing.json"
    request_path.write_bytes(serialized)
    output_path.write_text("existing", encoding="utf-8")
    cli = CliRunner().invoke(
        m2002.m2002_app,
        ["reconcile", str(request_path), "--output", str(output_path)],
    )
    assert cli.exit_code != 0
    assert "output already exists" in cli.output

    invalid_request = tmp_path / "invalid-request.json"
    invalid_request.write_text("{}", encoding="utf-8")
    failed_cli = CliRunner().invoke(m2002.m2002_app, ["reconcile", str(invalid_request)])
    assert failed_cli.exit_code == 1
    assert "reconciliation failed" in failed_cli.output

    invalid_result = tmp_path / "invalid-result.json"
    invalid_result.write_text("{}", encoding="utf-8")
    failed_verify = CliRunner().invoke(m2002.m2002_app, ["verify", str(invalid_result)])
    assert failed_verify.exit_code == 1
    assert "verification failed" in failed_verify.output

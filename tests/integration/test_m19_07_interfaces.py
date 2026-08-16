"""API, CLI and plugin parity tests for M19-07."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    M1907ExportError,
    M1907Service,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    api as m1907_api,
)
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    cli as m1907_cli_module,
)

from ..contract.test_m19_07_deep import _request

_OK = 200
_UNPROCESSABLE = 422
_FORBIDDEN = 403


def test_api_schema_validate_export_and_verify_are_strict() -> None:
    request = _request().model_dump(mode="json")
    with TestClient(m1907_api.create_m1907_app()) as client:
        schema = client.get("/v1/contracts/M19-07/request/schema")
        assert schema.status_code == _OK
        assert schema.json()["x-glio-contract"]["parentTarget"] == "proteotype"
        validated = client.post("/v1/modules/M19-07/validate", json=request)
        assert validated.status_code == _OK
        exported = client.post("/v1/modules/M19-07/export", json=request)
        assert exported.status_code == _OK
        verified = client.post("/v1/modules/M19-07/verify", json=exported.json())
        assert verified.status_code == _OK
        assert verified.json()["result_digest"] == exported.json()["result_digest"]


def test_api_sanitizes_invalid_json() -> None:
    with TestClient(m1907_api.create_m1907_app()) as client:
        response = client.post(
            "/v1/modules/M19-07/export",
            content=b"{\"not_closed\": true}",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == _UNPROCESSABLE
        assert response.json()["detail"] == "M19-07 request is invalid"


def test_api_handlers_cover_authentication_and_safe_operation_failure() -> None:
    request = _request()
    withheld = request.context.references.consent.model_copy(
        update={"state": ConsentState.WITHHELD}
    )
    denied = request.model_copy(
        update={
            "consent": withheld,
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"consent": withheld}
                    )
                }
            ),
        }
    )
    with TestClient(m1907_api.create_m1907_app()) as client:
        denied_response = client.post(
            "/v1/modules/M19-07/export", json=denied.model_dump(mode="json")
        )
        assert denied_response.status_code == _FORBIDDEN
        assert "consent" in denied_response.json()["detail"]
        invalid_result = client.post(
            "/v1/modules/M19-07/verify",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
        assert invalid_result.status_code == _UNPROCESSABLE
        assert invalid_result.json()["detail"] == "M19-07 result is invalid"

    class FailingService(M1907Service):
        def execute(self, _candidate: object):  # type: ignore[no-untyped-def]
            raise M1907ExportError

    with TestClient(m1907_api.create_m1907_app(FailingService())) as client:
        failed = client.post(
            "/v1/modules/M19-07/export", json=request.model_dump(mode="json")
        )
        assert failed.status_code == _UNPROCESSABLE
        assert failed.json()["detail"] == "M19-07 operation failed safely"


def test_cli_schema_no_overwrite_and_validate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    schema_path = tmp_path / "schema.json"
    runner = CliRunner()
    first = runner.invoke(
        m1907_cli_module.app,
        ["export-schema", "request", "--output", str(schema_path)],
    )
    assert first.exit_code == 0
    second = runner.invoke(
        m1907_cli_module.app,
        ["export-schema", "request", "--output", str(schema_path)],
    )
    assert second.exit_code != 0
    validated = runner.invoke(m1907_cli_module.app, ["validate", str(request_path)])
    assert validated.exit_code == 0


def test_cli_export_and_verify_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()
    exported = runner.invoke(m1907_cli_module.app, ["export", str(request_path)])
    assert exported.exit_code == 0
    result_path = tmp_path / "result.json"
    result_path.write_text(exported.stdout, encoding="utf-8")
    verified = runner.invoke(m1907_cli_module.app, ["verify", str(result_path)])
    assert verified.exit_code == 0

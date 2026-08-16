"""FastAPI, Typer, and plugin parity for M25-01."""

from __future__ import annotations

from typing import Any

from evals.m25_01.fixture import build_request, pending_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material.m25_01_reference_truth_benchmark_curator import (
    M2501Plugin,
    M2501Service,
    ReferenceTruthSubmission,
    ValidatedM2501Request,
    app,
    create_app,
)

_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422
_HTTP_NOT_FOUND = 404
_SCHEMA_COUNT = 9


def test_plugin_requires_submission_and_reuses_validated_token() -> None:
    plugin = M2501Plugin(M2501Service())
    validated = plugin.validate(ReferenceTruthSubmission(build_request()))

    assert isinstance(validated, ValidatedM2501Request)
    assert plugin.run(validated).status.value == "curated"


def test_plugin_parses_json_submission_once() -> None:
    plugin = M2501Plugin(M2501Service())
    payload = canonical_json_bytes(build_request())
    validated = plugin.validate(ReferenceTruthSubmission(payload))

    assert plugin.run(validated).package is not None


def test_api_schema_validate_curate_and_verify_parity() -> None:
    client = TestClient(create_app(M2501Service()))
    request_body = build_request().model_dump(mode="json")

    schemas = client.get("/v1/modules/M25-01/schemas")
    validated = client.post("/v1/modules/M25-01/validate", json=request_body)
    curated = client.post("/v1/modules/M25-01/curate", json=request_body)
    verified = client.post("/v1/modules/M25-01/verify", json=curated.json())

    assert schemas.status_code == _HTTP_OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    assert validated.status_code == _HTTP_OK
    assert curated.status_code == _HTTP_OK
    assert curated.json()["status"] == "curated"
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True


def test_api_sanitizes_invalid_and_unauthorized_requests() -> None:
    client = TestClient(create_app(M2501Service()))
    denied = build_request()
    support = denied.context.references.support.model_copy(update={"state": "rejected"})
    context = denied.context.model_copy(
        update={"references": denied.context.references.model_copy(update={"support": support})}
    )
    denied_body = denied.model_copy(update={"context": context}).model_dump(mode="json")

    invalid = client.post("/v1/modules/M25-01/validate", content=b"[]")
    unauthorized = client.post("/v1/modules/M25-01/curate", json=denied_body)
    unknown = client.get("/v1/modules/M25-01/schemas/not-a-contract")

    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert unauthorized.status_code == _HTTP_UNPROCESSABLE
    assert unknown.status_code == _HTTP_NOT_FOUND
    assert "Traceback" not in invalid.text


def test_cli_export_validate_curate_and_verify(tmp_path: Any) -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["export-schema", "request"]).exit_code == 0
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(build_request()))
    result_path = tmp_path / "result.json"

    assert runner.invoke(app, ["validate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(app, ["curate", str(request_path), "--output", str(result_path)]).exit_code
        == 0
    )
    assert runner.invoke(app, ["verify", str(result_path)]).exit_code == 0


def test_cli_abstention_and_no_overwrite(tmp_path: Any) -> None:
    runner = CliRunner()
    request_path = tmp_path / "pending.json"
    request_path.write_bytes(canonical_json_bytes(pending_request()))
    result_path = tmp_path / "pending-result.json"

    completed = runner.invoke(app, ["curate", str(request_path), "--output", str(result_path)])
    repeated = runner.invoke(app, ["curate", str(request_path), "--output", str(result_path)])

    assert completed.exit_code == 1
    assert result_path.exists()
    assert repeated.exit_code != 0

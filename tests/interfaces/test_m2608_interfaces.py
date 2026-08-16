"""FastAPI, SDK, Typer, and strict-plugin parity tests for M26-08."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m26_08.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ExecutionContext, UpstreamDecisionState
from glio_proteogen.modules.c20_biomarker_panel.m26_08_retirement_archival_knowledge_transfer import (  # noqa: E501
    M2608Client,
    M2608RetirementService,
    app,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_08_retirement_archival_knowledge_transfer.cli import (  # noqa: E501
    app as cli_app,
)
from tests.runtime.test_m2608_runtime import _request

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_UNPROCESSABLE = 422
HTTP_NOT_FOUND = 404
SCHEMA_COUNT = 10


def test_fastapi_schema_validate_retire_and_verify_routes() -> None:
    request = _request()
    body = request.model_dump_json()

    with TestClient(app) as client:
        schemas = client.get("/v1/modules/M26-08/schemas")
        request_schema = client.get("/v1/modules/M26-08/schemas/request")
        validated = client.post("/v1/modules/M26-08/validate", content=body)
        retired = client.post("/v1/modules/M26-08/retire", content=body)
        verified = client.post(
            "/v1/modules/M26-08/verify",
            content=canonical_json_bytes({"result": retired.json()}),
        )

    assert schemas.status_code == HTTP_OK
    assert len(schemas.json()) == SCHEMA_COUNT
    assert request_schema.status_code == HTTP_OK
    assert validated.status_code == HTTP_OK
    assert retired.status_code == HTTP_OK
    assert retired.json()["status"] == "executed"
    assert verified.status_code == HTTP_OK
    assert verified.json()["verified"] is True


def test_fastapi_rejects_duplicate_keys_and_unknown_schema() -> None:
    with TestClient(app) as client:
        duplicate = client.post(
            "/v1/modules/M26-08/validate",
            content=b'{"request_id":"a","request_id":"b"}',
        )
        unknown = client.get("/v1/modules/M26-08/schemas/unknown")

    assert duplicate.status_code == HTTP_UNPROCESSABLE
    assert "strict" not in duplicate.text.lower()
    assert unknown.status_code == HTTP_NOT_FOUND


def _context_with_quality_rejected() -> ExecutionContext:
    request = _request()
    quality = request.context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = request.context.references.model_copy(update={"quality": quality})
    return request.context.model_copy(update={"references": references})


def test_fastapi_rejects_non_object_and_tampered_replay() -> None:
    result = M2608RetirementService().retire(_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with TestClient(app) as client:
        non_object = client.post("/v1/modules/M26-08/verify", content=b"[]")
        invalid = client.post(
            "/v1/modules/M26-08/verify",
            content=canonical_json_bytes({"result": tampered}),
        )
        malformed = client.post("/v1/modules/M26-08/verify", content=b"not-json")

    assert non_object.status_code == HTTP_UNPROCESSABLE
    assert invalid.status_code == HTTP_UNPROCESSABLE
    assert malformed.status_code == HTTP_UNPROCESSABLE


def test_fastapi_sanitizes_failed_preflight() -> None:
    request = _request(context=_context_with_quality_rejected())
    with TestClient(app) as client:
        validated = client.post("/v1/modules/M26-08/validate", content=request.model_dump_json())
        retired = client.post("/v1/modules/M26-08/retire", content=request.model_dump_json())

    assert validated.status_code == HTTP_UNPROCESSABLE
    assert retired.status_code == HTTP_UNPROCESSABLE
    assert "ValidationError" not in validated.text


def test_sdk_preserves_service_canonical_result() -> None:
    request = _request()
    service_result = M2608RetirementService().retire(request)
    client_result = M2608Client().retire(request)

    assert client_result.model_dump(mode="json") == service_result.model_dump(mode="json")
    assert M2608Client().verify(client_result).result_digest == client_result.result_digest
    assert M2608Client().validate(request) == request
    assert M2608Client().retire_json(request)["result_digest"] == client_result.result_digest


def test_typer_exports_schema_and_refuses_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    schema_path = tmp_path / "request.schema.json"

    exported = runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)])
    stdout_export = runner.invoke(cli_app, ["export-schema", "request"])
    refused = runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)])

    assert exported.exit_code == 0, exported.stdout
    assert stdout_export.exit_code == 0
    assert json.loads(schema_path.read_text(encoding="utf-8"))["x-glio-contract"]["provisionalAbi"]
    assert refused.exit_code != 0
    assert "overwrite" in refused.output.lower()


def test_typer_retire_then_verify_canonical_file(tmp_path: Path) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(_request()))

    retired = runner.invoke(cli_app, ["retire", str(request_path), "--output", str(result_path)])
    verified = runner.invoke(cli_app, ["verify", str(result_path)])

    assert retired.exit_code == 0, retired.stdout
    assert verified.exit_code == 0, verified.stdout
    assert json.loads(verified.stdout)["verified"] is True


def test_typer_rejects_unknown_schema_and_abstention(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(cli_app, ["export-schema", "unknown"])
    request_path = tmp_path / "abstained-request.json"
    request_path.write_bytes(canonical_json_bytes(_request(criterion_satisfied=False)))
    abstained = runner.invoke(cli_app, ["retire", str(request_path)])

    assert unknown.exit_code != 0
    assert abstained.exit_code == 1


def test_typer_rejects_invalid_request_and_tampered_result(tmp_path: Path) -> None:
    runner = CliRunner()
    invalid_request = tmp_path / "invalid-request.json"
    invalid_request.write_bytes(b'{"request_id":"a","request_id":"b"}')
    rejected = runner.invoke(cli_app, ["validate", str(invalid_request)])
    result_path = tmp_path / "tampered.json"
    result_path.write_text('{"result_digest":"sha256:' + "f" * 64 + '"}', encoding="utf-8")
    invalid_result = runner.invoke(cli_app, ["verify", str(result_path)])

    assert rejected.exit_code != 0
    assert invalid_result.exit_code != 0


def test_typer_validate_and_sanitizes_preflight_failure(tmp_path: Path) -> None:
    runner = CliRunner()
    valid_path = tmp_path / "valid-request.json"
    valid_path.write_bytes(canonical_json_bytes(_request()))
    validated = runner.invoke(cli_app, ["validate", str(valid_path)])
    rejected_path = tmp_path / "rejected-request.json"
    rejected_path.write_bytes(
        canonical_json_bytes(_request(context=_context_with_quality_rejected()))
    )
    rejected = runner.invoke(cli_app, ["retire", str(rejected_path)])
    rejected_validate = runner.invoke(cli_app, ["validate", str(rejected_path)])

    assert validated.exit_code == 0
    assert rejected.exit_code != 0
    assert rejected_validate.exit_code != 0


def test_typer_replay_rejects_canonical_tamper(tmp_path: Path) -> None:
    runner = CliRunner()
    result = M2608RetirementService().retire(_request())
    tampered = result.model_copy(update={"result_id": "result.m2608.tampered"})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})
    result_path = tmp_path / "tampered-result.json"
    result_path.write_bytes(canonical_json_bytes(tampered))
    verified = runner.invoke(cli_app, ["verify", str(result_path)])

    assert verified.exit_code != 0

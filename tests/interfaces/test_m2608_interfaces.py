"""FastAPI, SDK, Typer, and strict-plugin parity tests for M26-08."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
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
        validated = client.post("/v1/modules/M26-08/validate", content=body)
        retired = client.post("/v1/modules/M26-08/retire", content=body)
        verified = client.post(
            "/v1/modules/M26-08/verify",
            content=canonical_json_bytes({"result": retired.json()}),
        )

    assert schemas.status_code == HTTP_OK
    assert len(schemas.json()) == SCHEMA_COUNT
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


def test_sdk_preserves_service_canonical_result() -> None:
    request = _request()
    service_result = M2608RetirementService().retire(request)
    client_result = M2608Client().retire(request)

    assert client_result.model_dump(mode="json") == service_result.model_dump(mode="json")
    assert M2608Client().verify(client_result).result_digest == client_result.result_digest


def test_typer_exports_schema_and_refuses_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    schema_path = tmp_path / "request.schema.json"

    exported = runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)])
    refused = runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)])

    assert exported.exit_code == 0, exported.stdout
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

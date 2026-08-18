"""FastAPI, Typer, and strict plugin parity for M23-01."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m23_01 import canonical_request_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material.m23_01_reference_truth_benchmark_curator import (
    M2301Plugin,
    M2301Service,
    ReferenceTruthSubmission,
    api,
    cli,
)
from tests.contract.test_m23_01_deep import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_SCHEMA_COUNT = 9


def test_fastapi_validate_curate_and_schema_routes_are_strict() -> None:
    request = _request()
    client = TestClient(api.create_app())
    body = request.model_dump_json()
    schemas = client.get("/v1/modules/M23-01/schemas")
    assert schemas.status_code == _HTTP_OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    validated = client.post(
        "/v1/modules/M23-01/validate",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert validated.status_code == _HTTP_OK
    curated = client.post(
        "/v1/modules/M23-01/curate",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert curated.status_code == _HTTP_OK
    assert curated.json()["request_digest"] == canonical_request_digest(request)
    verified = client.post(
        "/v1/modules/M23-01/verify",
        content=json.dumps(curated.json()).encode(),
        headers={"content-type": "application/json"},
    )
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M23-01/schemas/unknown").status_code == _HTTP_NOT_FOUND


def test_fastapi_sanitizes_malformed_json_and_tampered_replay() -> None:
    client = TestClient(api.create_app())
    malformed = client.post("/v1/modules/M23-01/verify", content=b"not-json")
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    request = _request()
    result = M2301Service().execute(request).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "f" * 64
    tampered = client.post("/v1/modules/M23-01/verify", json=result)
    assert tampered.status_code == _HTTP_UNPROCESSABLE


def test_typer_export_validate_curate_and_verify(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_bytes(canonical_json_bytes(request))
    runner = CliRunner()
    exported = runner.invoke(cli.app, ["export-schema", "request"])
    assert exported.exit_code == 0
    validated = runner.invoke(cli.app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    curated = runner.invoke(cli.app, ["curate", str(request_path), "--output", str(result_path)])
    assert curated.exit_code == 0
    verified = runner.invoke(cli.app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    overwrite = runner.invoke(cli.app, ["curate", str(request_path), "--output", str(result_path)])
    assert overwrite.exit_code != 0


def test_plugin_is_parse_once_and_token_bound() -> None:
    request = _request()
    plugin = M2301Plugin(M2301Service())
    token = plugin.validate(ReferenceTruthSubmission(request.model_dump_json().encode()))
    result = plugin.run(token)
    assert result.request_digest == canonical_request_digest(request)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M23-01"

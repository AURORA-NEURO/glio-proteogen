"""FastAPI and Typer parity tests for M10-08."""

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1008 import create_m1008_app, m1008_app
from glio_proteogen.modules.c10_pathway_proteotype_factors import (
    m10_08_evidence_explanation_publisher as m1008_runtime,
)
from tests.modules.c10_pathway_proteotype_factors.test_m10_08_runtime import _request

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_CONFLICT = 409
CLI_INVALID = 2


def test_fastapi_validate_publish_verify_and_schema_parity() -> None:
    client = TestClient(create_m1008_app(m1008_runtime.M1008EvidencePublisherService()))
    payload = _request().model_dump(mode="json")
    validated = client.post("/v1/m10-08/validate", json=payload)
    assert validated.status_code == HTTP_OK
    published = client.post("/v1/m10-08/publish", json=payload)
    assert published.status_code == HTTP_OK
    result = published.json()
    verified = client.post("/v1/m10-08/verify", json=result)
    assert verified.status_code == HTTP_OK
    assert verified.json()["verified"] is True
    schema = client.get("/v1/m10-08/schema/output")
    assert schema.status_code == HTTP_OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True


def test_fastapi_sanitizes_duplicate_auth_and_tamper_errors() -> None:
    client = TestClient(create_m1008_app())
    duplicate = client.post(
        "/v1/m10-08/validate",
        content=b'{"context":{},"context":{}}',
        headers={"content-type": "application/json"},
    )
    assert duplicate.status_code == HTTP_BAD_REQUEST
    assert duplicate.json()["detail"]["type"] == "json_duplicate_key"
    unauthorized = _request().model_dump(mode="json")
    unauthorized["context"]["references"]["support"]["state"] = "rejected"
    rejected = client.post("/v1/m10-08/validate", json=unauthorized)
    assert rejected.status_code == HTTP_FORBIDDEN
    result = client.post("/v1/m10-08/publish", json=_request().model_dump(mode="json")).json()
    result["result_digest"] = "sha256:" + ("b" * 64)
    tampered = client.post("/v1/m10-08/verify", json=result)
    assert tampered.status_code == HTTP_CONFLICT


def test_typer_export_validate_and_duplicate_error() -> None:
    runner = CliRunner()
    schema = runner.invoke(m1008_app, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M10-08"
    request_json = _request().model_dump_json()
    validated = runner.invoke(m1008_app, ["validate", "-"], input=request_json)
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["valid"] is True
    duplicate = runner.invoke(
        m1008_app,
        ["validate", "-"],
        input='{"request_id":"one","request_id":"two"}',
    )
    assert duplicate.exit_code == CLI_INVALID
    assert "json_duplicate_key" in duplicate.stderr

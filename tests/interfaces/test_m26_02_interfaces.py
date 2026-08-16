"""FastAPI/Typer parity and hostile-input tests for M26-02."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.api import (
    create_m2602_app,
)
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.cli import app
from tests.runtime.test_m26_02_runtime import _request

_HTTP_OK = 200
_HTTP_BAD_REQUEST = 400


def _encoded_request() -> bytes:
    return json.dumps(_request().model_dump(mode="json"), sort_keys=True).encode()


def test_fastapi_validate_construct_verify_and_schema() -> None:
    client = TestClient(create_m2602_app())
    raw = _encoded_request()
    validated = client.post("/m26-02/validate", content=raw)
    assert validated.status_code == _HTTP_OK
    constructed = client.post("/m26-02/construct", content=raw)
    assert constructed.status_code == _HTTP_OK
    result = constructed.json()
    verified = client.post("/m26-02/verify", json=result)
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    schema = client.get("/m26-02/schema/request")
    assert schema.status_code == _HTTP_OK
    assert schema.json()["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M26-02"


def test_fastapi_duplicate_keys_are_sanitized_and_rejected() -> None:
    client = TestClient(create_m2602_app())
    response = client.post("/m26-02/validate", content=b'{"request_id":1,"request_id":2}')
    assert response.status_code == _HTTP_BAD_REQUEST
    assert response.json()["detail"]["type"] == "json_duplicate_key"
    assert "request_id" not in response.text


def test_typer_validate_construct_export_and_no_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_bytes(_encoded_request())
    runner = CliRunner()
    validated = runner.invoke(app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    result_path = tmp_path / "result.json"
    constructed = runner.invoke(app, ["construct", str(request_path), "--output", str(result_path)])
    assert constructed.exit_code == 0
    verified = runner.invoke(app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    schema_path = tmp_path / "schema.json"
    exported = runner.invoke(app, ["export-schema", "request", "--output", str(schema_path)])
    assert exported.exit_code == 0
    refused = runner.invoke(app, ["export-schema", "request", "--output", str(schema_path)])
    assert refused.exit_code != 0

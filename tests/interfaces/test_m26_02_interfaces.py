"""FastAPI/Typer parity and hostile-input tests for M26-02."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.api import (
    create_m2602_app,
)
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.cli import app
from tests.runtime.test_m26_02_runtime import _request

_HTTP_OK = 200
_HTTP_BAD_REQUEST = 400
_HTTP_UNPROCESSABLE = 422
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_CLI_VALIDATION_ERROR = 2
_CLI_ABSTENTION = 3


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


def test_fastapi_validation_authorization_and_route_errors() -> None:
    client = TestClient(create_m2602_app())
    invalid = client.post("/m26-02/validate", content=b'{"request_id":"only"}')
    assert invalid.status_code == _HTTP_UNPROCESSABLE
    denied = _request().model_copy(
        update={
            "context": _request().context.model_copy(
                update={
                    "references": _request().context.references.model_copy(
                        update={
                            "consent": _request().context.references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    denied_response = client.post(
        "/m26-02/validate",
        content=json.dumps(denied.model_dump(mode="json")).encode(),
    )
    assert denied_response.status_code == _HTTP_FORBIDDEN
    unknown_schema = client.get("/m26-02/schema/unknown")
    assert unknown_schema.status_code == _HTTP_NOT_FOUND
    invalid_verify = client.post("/m26-02/verify", content=b"not-json")
    assert invalid_verify.status_code == _HTTP_BAD_REQUEST


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
    stdout_schema = runner.invoke(app, ["export-schema", "request"])
    assert stdout_schema.exit_code == 0


def test_typer_error_and_abstention_paths(tmp_path: Path) -> None:
    runner = CliRunner()
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text('{"request_id":"only"}', encoding="utf-8")
    assert runner.invoke(app, ["validate", str(invalid_path)]).exit_code == _CLI_VALIDATION_ERROR
    assert runner.invoke(app, ["verify", str(invalid_path)]).exit_code == _CLI_VALIDATION_ERROR
    assert runner.invoke(app, ["export-schema", "unknown"]).exit_code != 0
    request_path = tmp_path / "abstain-request.json"
    request_path.write_bytes(
        json.dumps(_request(graph_digest="sha256:" + "f" * 64).model_dump(mode="json")).encode()
    )
    abstained = runner.invoke(app, ["construct", str(request_path)])
    assert abstained.exit_code == _CLI_ABSTENTION
    existing = tmp_path / "existing.json"
    existing.write_text("{}", encoding="utf-8")
    refused = runner.invoke(app, ["construct", str(request_path), "--output", str(existing)])
    assert refused.exit_code != 0


def test_api_verify_validation_error_is_sanitized() -> None:
    response = TestClient(create_m2602_app()).post("/m26-02/verify", content=b"{}")
    assert response.status_code == _HTTP_UNPROCESSABLE

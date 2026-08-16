"""FastAPI and Typer parity checks for M19-01."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1901 import app, m1901_app
from glio_proteogen.contracts.m19_01 import contract_json_schema
from glio_proteogen.kernel.canonical import canonical_json_bytes
from tests.contract.test_m19_01_deep import _request

HTTP_OK = 200
HTTP_UNSUPPORTED_MEDIA_TYPE = 415
HTTP_UNPROCESSABLE_ENTITY = 422


def test_fastapi_resolve_and_verify_are_canonical_and_strict() -> None:
    client = TestClient(app)
    request_bytes = canonical_json_bytes(_request())
    response = client.post(
        "/v1/modules/M19-01/resolve",
        content=request_bytes,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTP_OK
    result_bytes = canonical_json_bytes(response.json())
    verified = client.post(
        "/v1/modules/M19-01/verify",
        content=result_bytes,
        headers={"content-type": "application/json"},
    )
    assert verified.status_code == HTTP_OK
    assert verified.json() == response.json()
    schema_response = client.get("/v1/m19-01/schema/output").json()
    expected_schema = contract_json_schema("output")
    assert schema_response["$id"] == expected_schema["$id"]
    assert schema_response["x-glio-contract"] == {
        **expected_schema["x-glio-contract"],
        "closedCandidateOutcomeBuckets": ["selected", "rejected", "unresolved"],
        "safeAbstentionSupportStatuses": ["limited", "unsupported", "review_required"],
    }


def test_fastapi_rejects_wrong_media_type_and_duplicate_keys() -> None:
    client = TestClient(app)
    assert (
        client.post(
            "/v1/modules/M19-01/resolve", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == HTTP_UNSUPPORTED_MEDIA_TYPE
    )
    duplicate = b'{"request_id":"a","request_id":"b"}'
    response = client.post(
        "/v1/modules/M19-01/resolve",
        content=duplicate,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert "invalid JSON request" in response.text


def test_typer_schema_and_verify_commands_are_available(tmp_path) -> None:
    runner = CliRunner()
    schema = runner.invoke(m1901_app, ["export-schema", "output"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M19-01"
    result_path = tmp_path / "result.json"
    result = runner.invoke(
        m1901_app,
        ["resolve", str(tmp_path / "request.json"), "--output", str(result_path)],
    )
    assert result.exit_code != 0

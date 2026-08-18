"""M27-07 API/CLI parity smoke."""

import json

from evals.m27_07.fixture import build_request
from fastapi.testclient import TestClient

from glio_proteogen.modules.c27_complex_activity.m27_07_change_control import create_app

_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422


def test_api_schema_and_control_routes() -> None:
    client = TestClient(create_app())
    payload = build_request().model_dump(mode="json")
    assert client.get("/v1/contracts/M27-07/schema").status_code == _HTTP_OK
    assert client.post("/v1/modules/M27-07/validate", json=payload).status_code == _HTTP_OK
    response = client.post("/v1/modules/M27-07/control", json=payload)
    assert response.status_code == _HTTP_OK
    assert response.json()["status"] == "approved"


def test_api_verify_rejects_forged_result() -> None:
    client = TestClient(create_app())
    payload = build_request().model_dump(mode="json")
    result = client.post("/v1/modules/M27-07/control", json=payload).json()
    result["result_digest"] = "sha256:" + "f" * 64
    response = client.post("/v1/modules/M27-07/verify", content=json.dumps(result))
    assert response.status_code == _HTTP_UNPROCESSABLE


def test_api_verify_accepts_replayed_result() -> None:
    client = TestClient(create_app())
    payload = build_request().model_dump(mode="json")
    result = client.post("/v1/modules/M27-07/control", json=payload).json()
    response = client.post("/v1/modules/M27-07/verify", content=json.dumps(result))
    assert response.status_code == _HTTP_OK
    assert response.json()["verified"] is True

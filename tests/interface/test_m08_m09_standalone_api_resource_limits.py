"""Resource-boundary tests for the standalone M08-07/M09-07 FastAPI apps."""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_07_calibration_selective_prediction as m0807_module,
)
from glio_proteogen.modules.c09_complex_stoichiometry import (
    m09_07_calibration_selective_prediction as m0907_module,
)

m0807_api = importlib.import_module(f"{m0807_module.__name__}.api")
m0907_api = importlib.import_module(f"{m0907_module.__name__}.api")

_HTTP_BAD_REQUEST = 400
_HTTP_UNPROCESSABLE_ENTITY = 422
_HTTP_OK = 200


class _ExecutionRejectingService:
    """Minimal service seam for asserting sanitized execution failures."""

    @staticmethod
    def validate_request(_candidate: object) -> object:
        return object()

    @staticmethod
    def execute(_candidate: object) -> object:
        raise ValueError from None


@pytest.mark.parametrize(
    ("api_module", "path", "limit_name"),
    [
        (m0807_api, "/m08-07/calibrate", "M0807_MAX_CANONICAL_REQUEST_BYTES"),
        (m0907_api, "/m09-07/calibrate", "M0907_MAX_CANONICAL_REQUEST_BYTES"),
    ],
)
def test_standalone_calibration_routes_apply_request_ceiling(
    monkeypatch: pytest.MonkeyPatch,
    api_module: Any,
    path: str,
    limit_name: str,
) -> None:
    """Calibration routes reject over-limit payloads before contract parsing."""

    monkeypatch.setattr(api_module, limit_name, 1)
    client = TestClient(api_module.create_app())

    response = client.post(path, content=b"{}")

    assert response.status_code == _HTTP_BAD_REQUEST
    assert response.json()["error"]["type"] == "json_too_large"


@pytest.mark.parametrize(
    ("api_module", "path", "limit_name"),
    [
        (m0807_api, "/m08-07/verify", "M0807_MAX_CANONICAL_RESULT_BYTES"),
        (m0907_api, "/m09-07/verify", "M0907_MAX_CANONICAL_RESULT_BYTES"),
    ],
)
def test_standalone_verify_routes_apply_result_ceiling(
    monkeypatch: pytest.MonkeyPatch,
    api_module: Any,
    path: str,
    limit_name: str,
) -> None:
    """Verification envelopes use the result ceiling, not generic parser defaults."""

    monkeypatch.setattr(api_module, limit_name, 1)
    client = TestClient(api_module.create_app())

    response = client.post(path, content=b"{}")

    assert response.status_code == _HTTP_BAD_REQUEST
    assert response.json()["error"]["type"] == "json_too_large"


@pytest.mark.parametrize(
    ("api_module", "schema_path"),
    [
        (m0807_api, "/m08-07/schema"),
        (m0907_api, "/m09-07/schema"),
    ],
)
def test_standalone_schema_routes_remain_available(api_module: Any, schema_path: str) -> None:
    """The resource-boundary change does not remove public schema discovery."""

    response = TestClient(api_module.create_app()).get(schema_path)

    assert response.status_code == _HTTP_OK
    assert response.json()["schemas"]


@pytest.mark.parametrize(
    ("api_module", "path"),
    [
        (m0807_api, "/m08-07/calibrate"),
        (m0907_api, "/m09-07/calibrate"),
    ],
)
def test_standalone_calibration_sanitizes_execution_failure(api_module: Any, path: str) -> None:
    """A service failure cannot leak private execution details through the API."""

    client = TestClient(api_module.create_app(_ExecutionRejectingService()))

    response = client.post(path, json={"request": "fixture"})

    assert response.status_code == _HTTP_UNPROCESSABLE_ENTITY
    assert response.json() == {
        "error": {
            "message": "request does not satisfy the module contract",
            "type": "contract_rejected",
        }
    }

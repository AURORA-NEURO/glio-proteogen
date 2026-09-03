"""Standalone HTTP lifecycle and failure boundaries for the GBM model router."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from glio_proteogen.adapters import glioma_models as adapter

_PREFIX = adapter.GBM_AXES_ROUTE_PREFIX
_HTTP_OK = 200
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_UNSUPPORTED_MEDIA = 415
_HTTP_UNPROCESSABLE = 422
_HTTP_TOO_MANY_REQUESTS = 429
_UNAVAILABLE_RELEASE_MESSAGE = "an unavailable slot cannot be released"
_SENSITIVE_MODEL_DETAIL = "sensitive model detail"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(adapter.router)
    adapter.install_glioma_models_openapi(app)
    return app


class _UnavailableSlots:
    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        return False

    def release(self) -> None:
        raise AssertionError(_UNAVAILABLE_RELEASE_MESSAGE)


class _TrackingSlot:
    def __init__(self) -> None:
        self.released = False

    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        return True

    def release(self) -> None:
        self.released = True


def test_profile_demo_analyze_verify_and_openapi_lifecycle() -> None:
    with TestClient(_app()) as client:
        profile_response = client.get(f"{_PREFIX}/profile")
        demo_response = client.get(f"{_PREFIX}/demo")
        request = demo_response.json()
        request["bootstrap_replicates"] = 0
        analysis_response = client.post(f"{_PREFIX}/analyze", json=request)
        result = analysis_response.json()
        verification_response = client.post(
            f"{_PREFIX}/verify",
            json={"request": request, "result": result},
        )
        forged = {**result, "result_digest": "sha256:" + "f" * 64}
        forged_response = client.post(
            f"{_PREFIX}/verify",
            json={"request": request, "result": forged},
        )
        schema = client.get("/openapi.json").json()

    assert profile_response.status_code == _HTTP_OK
    assert demo_response.status_code == _HTTP_OK
    assert analysis_response.status_code == _HTTP_OK, analysis_response.text
    assert verification_response.status_code == _HTTP_OK
    assert verification_response.json()["verified"] is True
    assert forged_response.status_code == _HTTP_OK
    assert forged_response.json()["verified"] is False
    assert forged_response.json()["result_digest_match"] is False
    assert profile_response.headers["cache-control"] == "no-store"
    assert demo_response.headers["cache-control"] == "no-store"
    assert analysis_response.headers["cache-control"] == "no-store"
    assert verification_response.headers["cache-control"] == "no-store"
    assert analysis_response.headers["x-glio-result-digest"] == result["result_digest"]
    for suffix in ("profile", "demo", "analyze", "verify"):
        assert f"{_PREFIX}/{suffix}" in schema["paths"]
    replay_schema = schema["components"]["schemas"]["GbmReplayVerificationRequest"]
    assert {item["$ref"] for item in replay_schema["properties"]["result"]["anyOf"]} == {
        "#/components/schemas/GbmProteomicAxesResult",
        "#/components/schemas/UnverifiedGbmProteomicAxesResult",
    }


def test_transport_contract_rejects_wrong_media_duplicate_json_and_oversize() -> None:
    with TestClient(_app()) as client:
        wrong_media = client.post(
            f"{_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        duplicate_json = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"sample_id":"secret-a","sample_id":"secret-b"}',
            headers={"content-type": "application/json"},
        )
        oversized = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"padding":"' + b"x" * adapter.GBM_AXES_REQUEST_MAX_BYTES + b'"}',
            headers={"content-type": "application/json"},
        )

    assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA
    assert duplicate_json.status_code == _HTTP_UNPROCESSABLE
    assert "secret" not in duplicate_json.text
    assert oversized.status_code == _HTTP_PAYLOAD_TOO_LARGE
    assert all(response.headers["cache-control"] == "no-store" for response in (
        wrong_media,
        duplicate_json,
        oversized,
    ))


def test_capacity_is_admitted_before_body_parsing(monkeypatch) -> None:
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", _UnavailableSlots())
    with TestClient(_app()) as client:
        analysis = client.post(f"{_PREFIX}/analyze", content=b"not-json")
        verification = client.post(f"{_PREFIX}/verify", content=b"not-json")
    assert analysis.status_code == _HTTP_TOO_MANY_REQUESTS
    assert verification.status_code == _HTTP_TOO_MANY_REQUESTS
    assert analysis.headers["retry-after"] == "1"
    assert verification.headers["retry-after"] == "1"


def test_execute_sanitizes_failures_and_releases_capacity(monkeypatch) -> None:
    request = adapter.synthetic_demo_request().model_copy(update={"bootstrap_replicates": 0})
    slot = _TrackingSlot()
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)

    def fail(*_args, **_kwargs):
        raise ValueError(_SENSITIVE_MODEL_DETAIL)

    monkeypatch.setattr(adapter, "analyze_gbm_proteomic_axes", fail)
    with pytest.raises(HTTPException) as failure:
        adapter._execute(request)
    assert failure.value.status_code == _HTTP_UNPROCESSABLE
    assert "sensitive" not in str(failure.value.detail)
    assert slot.released is True

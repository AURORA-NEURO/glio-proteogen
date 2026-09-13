"""Standalone lifecycle and failure boundaries for the Neftel research router."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from glio_proteogen.adapters import neftel_programs as adapter
from glio_proteogen.research.neftel_protein_programs import synthetic_demo_request
from glio_proteogen.research.proteogenomic_state.cancellation import (
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

_PREFIX = adapter.NEFTEL_PROGRAMS_ROUTE_PREFIX
_HTTP_OK = 200
_HTTP_BAD_REQUEST = 400
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_UNSUPPORTED_MEDIA = 415
_HTTP_UNPROCESSABLE = 422
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_CLIENT_CLOSED = 499
_HTTP_INTERNAL_ERROR = 500
_HTTP_TIMEOUT = 504
_SENSITIVE_DETAIL = "patient-secret-model-detail"
_UNAVAILABLE_RELEASE_MESSAGE = "an unavailable slot cannot be released"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(adapter.router)
    adapter.install_neftel_programs_openapi(app)
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
    replay_schema = schema["components"]["schemas"]["NeftelReplayVerificationRequest"]
    assert {item["$ref"] for item in replay_schema["properties"]["result"]["anyOf"]} == {
        "#/components/schemas/ProteinProgramResult",
        "#/components/schemas/UnverifiedProteinProgramResult",
    }
    verify_schema = schema["paths"][f"{_PREFIX}/verify"]["post"]["requestBody"]
    assert verify_schema["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/NeftelReplayVerificationRequest"
    }


def test_transport_rejects_bad_metadata_media_duplicate_json_and_oversize() -> None:
    bad_length_request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": f"{_PREFIX}/analyze",
            "headers": [(b"content-length", b"invalid")],
        }
    )
    with pytest.raises(HTTPException) as bad_length:
        adapter._declared_content_length(
            bad_length_request,
            adapter.NEFTEL_PROGRAMS_REQUEST_MAX_BYTES,
        )

    with TestClient(_app()) as client:
        wrong_media = client.post(
            f"{_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        duplicate_json = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"sample_id":"patient-secret-a","sample_id":"patient-secret-b"}',
            headers={"content-type": "application/json"},
        )
        oversized = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"padding":"'
            + b"x" * adapter.NEFTEL_PROGRAMS_REQUEST_MAX_BYTES
            + b'"}',
            headers={"content-type": "application/json"},
        )

    assert bad_length.value.status_code == _HTTP_BAD_REQUEST
    assert bad_length.value.headers == {"Cache-Control": "no-store"}
    assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA
    assert duplicate_json.status_code == _HTTP_UNPROCESSABLE
    assert "patient-secret" not in duplicate_json.text
    assert oversized.status_code == _HTTP_PAYLOAD_TOO_LARGE
    assert all(
        response.headers["cache-control"] == "no-store"
        for response in (wrong_media, duplicate_json, oversized)
    )


def test_capacity_is_admitted_before_body_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", _UnavailableSlots())
    with TestClient(_app()) as client:
        analysis = client.post(f"{_PREFIX}/analyze", content=b"not-json")
        verification = client.post(f"{_PREFIX}/verify", content=b"not-json")
    assert analysis.status_code == _HTTP_TOO_MANY_REQUESTS
    assert verification.status_code == _HTTP_TOO_MANY_REQUESTS
    assert analysis.headers["retry-after"] == "1"
    assert verification.headers["retry-after"] == "1"
    assert analysis.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (ValueError(_SENSITIVE_DETAIL), _HTTP_UNPROCESSABLE),
        (InferenceCancelledError(_SENSITIVE_DETAIL), _HTTP_CLIENT_CLOSED),
        (InferenceDeadlineExceededError(_SENSITIVE_DETAIL), _HTTP_TIMEOUT),
        (RuntimeError(_SENSITIVE_DETAIL), _HTTP_INTERNAL_ERROR),
    ],
)
def test_execute_sanitizes_failures_and_releases_capacity(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_status: int,
) -> None:
    request = synthetic_demo_request()
    slot = _TrackingSlot()
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(adapter, "analyze_neftel_protein_programs", fail)
    with pytest.raises(HTTPException) as captured:
        adapter._execute(request)
    assert captured.value.status_code == expected_status
    assert "patient-secret" not in str(captured.value.detail)
    assert captured.value.headers is not None
    assert captured.value.headers["Cache-Control"] == "no-store"
    assert slot.released is True


def test_result_and_receipt_bounds_are_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    request = synthetic_demo_request()
    monkeypatch.setattr(adapter, "NEFTEL_PROGRAMS_RESULT_MAX_BYTES", 1)
    with pytest.raises(HTTPException) as result_bound:
        adapter._execute(request)
    assert result_bound.value.status_code == _HTTP_INTERNAL_ERROR

    monkeypatch.setattr(adapter, "NEFTEL_PROGRAMS_RESULT_MAX_BYTES", 1_048_576)
    monkeypatch.setattr(adapter, "NEFTEL_PROGRAMS_REPLAY_MAX_BYTES", 1)
    with pytest.raises(HTTPException) as receipt_bound:
        adapter._execute(request)
    assert receipt_bound.value.status_code == _HTTP_INTERNAL_ERROR

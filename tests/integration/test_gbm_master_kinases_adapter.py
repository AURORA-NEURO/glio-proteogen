"""Standalone lifecycle and failure boundaries for the GBM master-kinase router."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, cast

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from glio_proteogen.adapters import gbm_master_kinases as adapter
from glio_proteogen.research.gbm_master_kinases import (
    CatalogIntegrityError,
    ReplayVerificationRequest,
    analyze_master_kinases,
    synthetic_demo_request,
    verify_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.types import Message, Scope

_PREFIX = adapter.GBM_MASTER_KINASES_ROUTE_PREFIX
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
_MEBIBYTE = 1_024 * 1_024
_EXPECTED_CONCURRENCY = 2


def _raise_failure(failure: Exception, *_args: object, **_kwargs: object) -> None:
    raise failure


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(adapter.router)
    adapter.install_gbm_master_kinases_openapi(app)
    return app


def _stream_request(*bodies: bytes, disconnect: bool = False) -> Request:
    messages: list[Message]
    if disconnect:
        messages = [{"type": "http.disconnect"}]
    else:
        messages = [
            {
                "type": "http.request",
                "body": body,
                "more_body": index < len(bodies) - 1,
            }
            for index, body in enumerate(bodies)
        ]

    async def receive() -> Message:
        return messages.pop(0)

    scope = cast(
        "Scope",
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-type", b"application/json")],
        },
    )
    return Request(scope, receive)


def test_transport_limits_and_concurrency_are_exact() -> None:
    assert adapter.GBM_MASTER_KINASES_REQUEST_MAX_BYTES == 2 * _MEBIBYTE
    assert adapter.GBM_MASTER_KINASES_RESULT_MAX_BYTES == 2 * _MEBIBYTE
    assert adapter.GBM_MASTER_KINASES_REPLAY_MAX_BYTES == 4 * _MEBIBYTE
    assert adapter.GBM_MASTER_KINASES_MAX_CONCURRENT_ANALYSES == _EXPECTED_CONCURRENCY


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
    replay_schema = schema["components"]["schemas"]["MasterKinaseReplayVerificationRequest"]
    assert {item["$ref"] for item in replay_schema["properties"]["result"]["anyOf"]} == {
        "#/components/schemas/MasterKinaseResult",
        "#/components/schemas/UnverifiedMasterKinaseResult",
    }
    verify_schema = schema["paths"][f"{_PREFIX}/verify"]["post"]["requestBody"]
    assert verify_schema["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MasterKinaseReplayVerificationRequest"
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
            adapter.GBM_MASTER_KINASES_REQUEST_MAX_BYTES,
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
            content=b'{"padding":"' + b"x" * adapter.GBM_MASTER_KINASES_REQUEST_MAX_BYTES + b'"}',
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


def test_stream_bounds_disconnect_and_optional_content_length() -> None:
    no_length = _stream_request(b"{}")
    adapter._declared_content_length(no_length, 2)

    negative_length = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-length", b"-1")],
        }
    )
    with pytest.raises(HTTPException) as negative:
        adapter._declared_content_length(negative_length, 2)
    assert negative.value.status_code == _HTTP_BAD_REQUEST

    with pytest.raises(HTTPException) as streamed:
        asyncio.run(adapter._bounded_body(_stream_request(b"ab", b"cd"), 3))
    assert streamed.value.status_code == _HTTP_PAYLOAD_TOO_LARGE

    with pytest.raises(HTTPException) as disconnected:
        asyncio.run(adapter._bounded_body(_stream_request(disconnect=True), 3))
    assert disconnected.value.status_code == _HTTP_CLIENT_CLOSED


class _CheckpointFailure:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure

    def remaining_seconds(self) -> None:
        return None

    def checkpoint(self) -> None:
        raise self.failure


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (InferenceDeadlineExceededError(_SENSITIVE_DETAIL), _HTTP_TIMEOUT),
        (InferenceCancelledError(_SENSITIVE_DETAIL), _HTTP_CLIENT_CLOSED),
    ],
)
def test_typed_body_maps_cooperative_failures(
    failure: Exception,
    expected_status: int,
) -> None:
    request = synthetic_demo_request()
    body = request.model_dump_json().encode("utf-8")
    cancellation = cast(
        "CancellationContext",
        _CheckpointFailure(failure),
    )
    with pytest.raises(HTTPException) as captured:
        asyncio.run(
            adapter._typed_body(
                _stream_request(body),
                adapter._REQUEST_ADAPTER,
                adapter.GBM_MASTER_KINASES_REQUEST_MAX_BYTES,
                cancellation,
            )
        )
    assert captured.value.status_code == expected_status


def test_typed_body_maps_transport_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def timeout(_request: Request, _max_bytes: int) -> bytes:
        raise TimeoutError

    monkeypatch.setattr(adapter, "_bounded_body", timeout)
    with pytest.raises(HTTPException) as captured:
        asyncio.run(
            adapter._typed_body(
                _stream_request(b"{}"),
                adapter._REQUEST_ADAPTER,
                adapter.GBM_MASTER_KINASES_REQUEST_MAX_BYTES,
                CancellationContext(),
            )
        )
    assert captured.value.status_code == _HTTP_TIMEOUT


def test_disconnect_watcher_cancels_context() -> None:
    cancellation = CancellationContext()
    asyncio.run(
        adapter._watch_disconnect(
            _stream_request(disconnect=True),
            cancellation,
            asyncio.Event(),
        )
    )
    with pytest.raises(InferenceCancelledError):
        cancellation.checkpoint()


@pytest.mark.parametrize(
    ("path", "target"),
    [("profile", "algorithm_profile"), ("demo", "synthetic_demo_request")],
)
def test_read_endpoints_sanitize_integrity_failures(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    target: str,
) -> None:
    def fail() -> None:
        raise RuntimeError(_SENSITIVE_DETAIL)

    monkeypatch.setattr(adapter, target, fail)
    with TestClient(_app()) as client:
        response = client.get(f"{_PREFIX}/{path}")
    assert response.status_code == _HTTP_INTERNAL_ERROR
    assert response.headers["cache-control"] == "no-store"
    assert "patient-secret" not in response.text


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
        (CatalogIntegrityError(_SENSITIVE_DETAIL), _HTTP_INTERNAL_ERROR),
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

    monkeypatch.setattr(adapter, "analyze_master_kinases", fail)
    with pytest.raises(HTTPException) as captured:
        adapter._execute(request)
    assert captured.value.status_code == expected_status
    assert "patient-secret" not in str(captured.value.detail)
    assert captured.value.headers is not None
    assert captured.value.headers["Cache-Control"] == "no-store"
    assert slot.released is True


def test_result_and_receipt_bounds_are_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    request = synthetic_demo_request()
    monkeypatch.setattr(adapter, "GBM_MASTER_KINASES_RESULT_MAX_BYTES", 1)
    with pytest.raises(HTTPException) as result_bound:
        adapter._execute(request)
    assert result_bound.value.status_code == _HTTP_INTERNAL_ERROR

    monkeypatch.setattr(adapter, "GBM_MASTER_KINASES_RESULT_MAX_BYTES", 1_048_576)
    monkeypatch.setattr(adapter, "GBM_MASTER_KINASES_REPLAY_MAX_BYTES", 1)
    with pytest.raises(HTTPException) as receipt_bound:
        adapter._execute(request)
    assert receipt_bound.value.status_code == _HTTP_INTERNAL_ERROR


def test_direct_execute_and_verification_capacity_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    result = analyze_master_kinases(request)
    envelope = ReplayVerificationRequest(request=request, result=result)
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", _UnavailableSlots())
    with pytest.raises(HTTPException) as analysis:
        adapter._execute(request)
    with pytest.raises(HTTPException) as verification:
        adapter._execute_verification(envelope)
    assert analysis.value.status_code == _HTTP_TOO_MANY_REQUESTS
    assert verification.value.status_code == _HTTP_TOO_MANY_REQUESTS


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (ValueError(_SENSITIVE_DETAIL), _HTTP_UNPROCESSABLE),
        (CatalogIntegrityError(_SENSITIVE_DETAIL), _HTTP_INTERNAL_ERROR),
        (InferenceCancelledError(_SENSITIVE_DETAIL), _HTTP_CLIENT_CLOSED),
        (InferenceDeadlineExceededError(_SENSITIVE_DETAIL), _HTTP_TIMEOUT),
        (RuntimeError(_SENSITIVE_DETAIL), _HTTP_INTERNAL_ERROR),
    ],
)
def test_verification_sanitizes_failures_and_releases_capacity(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_status: int,
) -> None:
    request = synthetic_demo_request()
    envelope = ReplayVerificationRequest(request=request, result=analyze_master_kinases(request))
    slot = _TrackingSlot()
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(adapter, "verify_replay", fail)
    with pytest.raises(HTTPException) as captured:
        adapter._execute_verification(envelope)
    assert captured.value.status_code == expected_status
    assert "patient-secret" not in str(captured.value.detail)
    assert slot.released is True


def test_verification_result_bound_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    request = synthetic_demo_request()
    result = analyze_master_kinases(request)
    envelope = ReplayVerificationRequest(request=request, result=result)
    verification = verify_replay(envelope)
    monkeypatch.setattr(adapter, "verify_replay", lambda *_args, **_kwargs: verification)
    monkeypatch.setattr(adapter, "GBM_MASTER_KINASES_RESULT_MAX_BYTES", 1)
    with pytest.raises(HTTPException) as captured:
        adapter._execute_verification(envelope)
    assert captured.value.status_code == _HTTP_INTERNAL_ERROR


def test_cli_failures_and_bounds_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = synthetic_demo_request()
    result = analyze_master_kinases(request)
    envelope = ReplayVerificationRequest(request=request, result=result)
    verification = verify_replay(envelope)
    request_path = tmp_path / "request.json"
    receipt_path = tmp_path / "receipt.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    receipt_path.write_text(envelope.model_dump_json(), encoding="utf-8")

    for target in ("algorithm_profile", "synthetic_demo_request"):
        with monkeypatch.context() as context:
            context.setattr(
                adapter,
                target,
                partial(_raise_failure, RuntimeError(_SENSITIVE_DETAIL)),
            )
            command = adapter.cli_profile if target == "algorithm_profile" else adapter.cli_demo
            with pytest.raises(adapter.GbmMasterKinasesCliError):
                command()

    for failure in (ValueError(_SENSITIVE_DETAIL), RuntimeError(_SENSITIVE_DETAIL)):
        with monkeypatch.context() as context:
            context.setattr(
                adapter,
                "analyze_master_kinases",
                partial(_raise_failure, failure),
            )
            with pytest.raises(adapter.GbmMasterKinasesCliError):
                adapter.cli_analyze(request_path)
        with monkeypatch.context() as context:
            context.setattr(
                adapter,
                "verify_replay",
                partial(_raise_failure, failure),
            )
            with pytest.raises(adapter.GbmMasterKinasesCliError):
                adapter.cli_verify(receipt_path)

    with monkeypatch.context() as context:
        context.setattr(adapter, "analyze_master_kinases", lambda *_args, **_kwargs: result)
        context.setattr(adapter, "GBM_MASTER_KINASES_RESULT_MAX_BYTES", 1)
        with pytest.raises(adapter.GbmMasterKinasesCliError):
            adapter.cli_analyze(request_path)
    with monkeypatch.context() as context:
        context.setattr(adapter, "analyze_master_kinases", lambda *_args, **_kwargs: result)
        context.setattr(adapter, "GBM_MASTER_KINASES_REPLAY_MAX_BYTES", 1)
        with pytest.raises(adapter.GbmMasterKinasesCliError):
            adapter.cli_analyze(request_path)
    with monkeypatch.context() as context:
        context.setattr(adapter, "verify_replay", lambda *_args, **_kwargs: verification)
        context.setattr(adapter, "GBM_MASTER_KINASES_RESULT_MAX_BYTES", 1)
        with pytest.raises(adapter.GbmMasterKinasesCliError):
            adapter.cli_verify(receipt_path)

"""Isolated HTTP/CLI lifecycle and hard guards for the KNCC factor graph."""

from __future__ import annotations

import asyncio
import json
from functools import partial
from threading import Event as ThreadEvent
from typing import TYPE_CHECKING, cast

import pytest
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient
from starlette.requests import Request
from typer.testing import CliRunner

from glio_proteogen.adapters import gbm_factor_graph as adapter
from glio_proteogen.adapters.api import _CENTRAL_ROUTE_LIMITS, _MODEL_ROUTE_LIMITS
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.research.kncc_gbm_factor_graph.contracts import (
    DEMO_ID,
    PROFILE_ID,
    KnccGbmFactorGraphReplayVerificationRequest,
    KnccGbmFactorGraphReplayVerificationResult,
    KnccGbmFactorGraphRequest,
    KnccGbmFactorGraphResult,
)
from glio_proteogen.research.kncc_gbm_factor_graph.demo import synthetic_demo_request
from glio_proteogen.research.kncc_gbm_factor_graph.errors import (
    KnccGbmFactorGraphInferenceError,
    KnccGbmFactorGraphProfileIntegrityError,
    KnccGbmFactorGraphReplayError,
)
from glio_proteogen.research.kncc_gbm_factor_graph.service import (
    analyze_kncc_gbm_factor_graph,
    verify_kncc_gbm_factor_graph_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.types import Message, Scope

_PREFIX = adapter.GBM_FACTOR_GRAPH_ROUTE_PREFIX
_MEBIBYTE = 1_024 * 1_024
_SENSITIVE = "patient-sensitive-canary"
_HTTP_OK = 200
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_UNSUPPORTED_MEDIA = 415
_HTTP_UNPROCESSABLE = 422
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_CLIENT_CLOSED = 499
_HTTP_INTERNAL_ERROR = 500
_HTTP_UNAVAILABLE = 503
_HTTP_TIMEOUT = 504
_EXPECTED_TIMEOUT_SECONDS = 120.0
_UNAVAILABLE_RELEASE_MESSAGE = "an unavailable slot cannot be released"

Receipt = tuple[
    KnccGbmFactorGraphRequest,
    KnccGbmFactorGraphResult,
    KnccGbmFactorGraphReplayVerificationResult,
]


class _UnavailableSlots:
    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        return False

    def release(self) -> None:
        raise AssertionError(_UNAVAILABLE_RELEASE_MESSAGE)


class _TrackingSlot:
    def __init__(self) -> None:
        self.acquisitions = 0
        self.releases = 0
        self.released = False

    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        self.acquisitions += 1
        return True

    def release(self) -> None:
        self.releases += 1
        self.released = True


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


class _DisconnectedRequest:
    async def is_disconnected(self) -> bool:
        return True


def _raise_failure(failure: Exception, *_args: object, **_kwargs: object) -> None:
    raise failure


def _disconnect_after_one_poll_request() -> tuple[Request, list[Message]]:
    messages: list[Message] = [
        {"type": "http.request", "body": b"", "more_body": False},
        {"type": "http.disconnect"},
    ]

    async def receive() -> Message:
        return messages.pop(0)

    scope = cast(
        "Scope",
        {
            "type": "http",
            "method": "POST",
            "path": f"{_PREFIX}/analyze",
            "headers": [(b"content-type", b"application/json")],
        },
    )
    return Request(scope, receive), messages


@pytest.fixture(scope="module")
def real_receipt() -> Receipt:
    request = synthetic_demo_request()
    result = analyze_kncc_gbm_factor_graph(request)
    verification = verify_kncc_gbm_factor_graph_replay(
        KnccGbmFactorGraphReplayVerificationRequest(request=request, result=result)
    )
    assert verification.verified is True
    return request, result, verification


def _app() -> FastAPI:
    app = FastAPI()
    adapter.mount_gbm_factor_graph(app)
    adapter.install_gbm_factor_graph_openapi(app)
    return app


def test_exact_limits_live_outside_the_v1_catalog_registry() -> None:
    assert adapter.GBM_FACTOR_GRAPH_REQUEST_MAX_BYTES == 4 * _MEBIBYTE
    assert adapter.GBM_FACTOR_GRAPH_RESULT_MAX_BYTES == 8 * _MEBIBYTE
    assert adapter.GBM_FACTOR_GRAPH_REPLAY_MAX_BYTES == 16 * _MEBIBYTE
    assert adapter.GBM_FACTOR_GRAPH_MAX_CONCURRENT_ANALYSES == 1
    assert adapter.GBM_FACTOR_GRAPH_TIMEOUT_SECONDS == _EXPECTED_TIMEOUT_SECONDS
    assert _PREFIX not in _MODEL_ROUTE_LIMITS
    assert f"{_PREFIX}/verify" not in _MODEL_ROUTE_LIMITS
    assert _CENTRAL_ROUTE_LIMITS[_PREFIX] == (4 * _MEBIBYTE, 8 * _MEBIBYTE)
    assert _CENTRAL_ROUTE_LIMITS[f"{_PREFIX}/verify"] == (
        16 * _MEBIBYTE,
        8 * _MEBIBYTE,
    )


def test_mount_preflights_profile_before_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    before = tuple(app.routes)
    monkeypatch.setattr(
        adapter,
        "algorithm_profile",
        partial(_raise_failure, KnccGbmFactorGraphProfileIntegrityError(_SENSITIVE)),
    )
    with pytest.raises(KnccGbmFactorGraphProfileIntegrityError, match=_SENSITIVE):
        adapter.mount_gbm_factor_graph(app)
    assert tuple(app.routes) == before


def test_http_lifecycle_headers_openapi_and_forgery(
    monkeypatch: pytest.MonkeyPatch,
    real_receipt: Receipt,
) -> None:
    request, result, verification = real_receipt
    forged_verification = verification.model_copy(
        update={"verified": False, "result_digest_match": False}
    )
    monkeypatch.setattr(adapter, "analyze_kncc_gbm_factor_graph", lambda *_a, **_k: result)
    monkeypatch.setattr(
        adapter,
        "verify_kncc_gbm_factor_graph_replay",
        lambda envelope, **_kwargs: (
            verification
            if envelope.result.result_digest == result.result_digest
            else forged_verification
        ),
    )
    with TestClient(_app()) as client:
        profile_response = client.get(f"{_PREFIX}/profile")
        demo_response = client.get(f"{_PREFIX}/demo")
        analysis_response = client.post(
            f"{_PREFIX}/analyze",
            json=request.model_dump(mode="json"),
        )
        result_document = analysis_response.json()
        verification_response = client.post(
            f"{_PREFIX}/verify",
            json={"request": request.model_dump(mode="json"), "result": result_document},
        )
        forged = json.loads(json.dumps(result_document))
        forged_profile_digest = "sha256:" + "e" * 64
        forged["profile_digest"] = forged_profile_digest
        forged["provenance"]["profile_digest"] = forged_profile_digest
        forged["result_digest"] = "sha256:" + "f" * 64
        forged_response = client.post(
            f"{_PREFIX}/verify",
            json={"request": request.model_dump(mode="json"), "result": forged},
        )
        schema = client.get("/openapi.json").json()

    assert profile_response.status_code == _HTTP_OK
    assert profile_response.json()["profile_id"] == PROFILE_ID
    assert demo_response.status_code == _HTTP_OK
    assert demo_response.json()["analysis_id"] == DEMO_ID
    assert analysis_response.status_code == _HTTP_OK
    assert verification_response.json()["verified"] is True
    assert forged_response.json()["verified"] is False
    assert analysis_response.headers["x-glio-result-digest"] == result.result_digest
    assert forged_response.headers["x-glio-profile-digest"] == result.profile_digest
    assert forged_response.headers["x-glio-profile-digest"] != forged_profile_digest
    for response in (
        profile_response,
        demo_response,
        analysis_response,
        verification_response,
        forged_response,
    ):
        assert response.headers["cache-control"] == "no-store"
    for suffix in ("profile", "demo", "analyze", "verify"):
        assert f"{_PREFIX}/{suffix}" in schema["paths"]
    replay = schema["components"]["schemas"]["KnccGbmFactorGraphReplayVerificationRequest"]
    assert {item["$ref"] for item in replay["properties"]["result"]["anyOf"]} == {
        "#/components/schemas/KnccGbmFactorGraphResult",
        "#/components/schemas/UnverifiedKnccGbmFactorGraphResult",
    }


def test_strict_json_media_capacity_and_size_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(_app()) as client:
        wrong_media = client.post(
            f"{_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        duplicate_json = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"analysis_id":"patient-a","analysis_id":"patient-b"}',
            headers={"content-type": "application/json"},
        )
        oversized = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"padding":"' + b"x" * adapter.GBM_FACTOR_GRAPH_REQUEST_MAX_BYTES + b'"}',
            headers={"content-type": "application/json"},
        )
    assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA
    assert duplicate_json.status_code == _HTTP_UNPROCESSABLE
    assert "patient-" not in duplicate_json.text
    assert oversized.status_code == _HTTP_PAYLOAD_TOO_LARGE

    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", _UnavailableSlots())
    with TestClient(_app()) as client:
        analysis = client.post(f"{_PREFIX}/analyze", content=b"not-json")
        verification = client.post(f"{_PREFIX}/verify", content=b"not-json")
    assert analysis.status_code == _HTTP_TOO_MANY_REQUESTS
    assert verification.status_code == _HTTP_TOO_MANY_REQUESTS
    assert analysis.headers["retry-after"] == "1"
    assert analysis.headers["cache-control"] == "no-store"


def test_runtime_guard_slow_body_deadline_maps_without_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body_started = False
    body_cancelled = False

    async def slow_body(_request: Request, _max_bytes: int) -> bytes:
        nonlocal body_cancelled, body_started
        body_started = True
        pending: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        try:
            return await pending
        finally:
            body_cancelled = True

    request = Request(
        cast(
            "Scope",
            {
                "type": "http",
                "method": "POST",
                "path": f"{_PREFIX}/analyze",
                "headers": [(b"content-type", b"application/json")],
            },
        )
    )
    expired = CancellationContext(deadline=0.0, clock=lambda: 0.0)
    monkeypatch.setattr(adapter, "_bounded_body", slow_body)

    with pytest.raises(HTTPException) as captured:
        asyncio.run(
            adapter._typed_body(
                request,
                adapter._REQUEST_ADAPTER,
                adapter.GBM_FACTOR_GRAPH_REQUEST_MAX_BYTES,
                expired,
            )
        )

    assert body_started is True
    assert body_cancelled is True
    assert captured.value.status_code == _HTTP_TIMEOUT
    assert captured.value.detail == adapter._TIMEOUT_MESSAGE
    assert captured.value.headers == {"Cache-Control": "no-store"}


def test_runtime_guard_disconnect_watcher_polls_and_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, pending_messages = _disconnect_after_one_poll_request()
    cancellation = CancellationContext()
    monkeypatch.setattr(adapter, "_DISCONNECT_POLL_SECONDS", 0.0)

    asyncio.run(adapter._watch_disconnect(request, cancellation, asyncio.Event()))

    assert pending_messages == []
    with pytest.raises(InferenceCancelledError):
        cancellation.checkpoint()


@pytest.mark.parametrize("endpoint_name", ["analyze", "verify"])
def test_runtime_guard_body_deadline_releases_endpoint_slot(
    monkeypatch: pytest.MonkeyPatch,
    endpoint_name: str,
) -> None:
    slot = _TrackingSlot()

    async def deadline(*_args: object, **_kwargs: object) -> object:
        raise adapter._http_error(_HTTP_TIMEOUT, adapter._TIMEOUT_MESSAGE)

    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)
    monkeypatch.setattr(adapter, "_typed_body", deadline)
    endpoint = getattr(adapter, endpoint_name)

    with pytest.raises(HTTPException) as captured:
        asyncio.run(endpoint(cast("Request", _ConnectedRequest()), Response()))

    assert captured.value.status_code == _HTTP_TIMEOUT
    assert captured.value.detail == adapter._TIMEOUT_MESSAGE
    assert captured.value.headers == {"Cache-Control": "no-store"}
    assert slot.acquisitions == 1
    assert slot.releases == 1


@pytest.mark.parametrize(
    ("endpoint_name", "service_name"),
    [
        ("analyze", "analyze_kncc_gbm_factor_graph"),
        ("verify", "verify_kncc_gbm_factor_graph_replay"),
    ],
)
def test_runtime_guard_disconnect_cancellation_reaches_service_and_releases_slot(
    monkeypatch: pytest.MonkeyPatch,
    endpoint_name: str,
    service_name: str,
) -> None:
    slot = _TrackingSlot()
    watcher_cancelled = ThreadEvent()
    observed_contexts: list[CancellationContext] = []
    original_cancel = CancellationContext.cancel

    async def typed_body(*_args: object, **_kwargs: object) -> object:
        return object()

    def observe_cancel(cancellation: CancellationContext) -> None:
        original_cancel(cancellation)
        watcher_cancelled.set()

    def cancelled_service(
        _value: object,
        *,
        cancellation: CancellationContext | None = None,
    ) -> None:
        assert cancellation is not None
        observed_contexts.append(cancellation)
        assert watcher_cancelled.wait(timeout=1.0)
        with pytest.raises(InferenceCancelledError):
            cancellation.checkpoint()
        raise InferenceCancelledError(_SENSITIVE)

    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)
    monkeypatch.setattr(adapter, "_typed_body", typed_body)
    monkeypatch.setattr(adapter, service_name, cancelled_service)
    monkeypatch.setattr(CancellationContext, "cancel", observe_cancel)
    endpoint = getattr(adapter, endpoint_name)

    with pytest.raises(HTTPException) as captured:
        asyncio.run(endpoint(cast("Request", _DisconnectedRequest()), Response()))

    assert len(observed_contexts) == 1
    assert observed_contexts[0].deadline is not None
    assert captured.value.status_code == _HTTP_CLIENT_CLOSED
    assert captured.value.detail == adapter._CANCELLED_MESSAGE
    assert _SENSITIVE not in str(captured.value.detail)
    assert captured.value.headers == {"Cache-Control": "no-store"}
    assert slot.acquisitions == 1
    assert slot.releases == 1


@pytest.mark.parametrize(
    ("endpoint_name", "service_name", "expected_detail"),
    [
        ("analyze", "analyze_kncc_gbm_factor_graph", adapter._ANALYSIS_ERROR_MESSAGE),
        ("verify", "verify_kncc_gbm_factor_graph_replay", adapter._REPLAY_ERROR_MESSAGE),
    ],
)
def test_runtime_guard_service_failure_releases_endpoint_slot(
    monkeypatch: pytest.MonkeyPatch,
    endpoint_name: str,
    service_name: str,
    expected_detail: str,
) -> None:
    slot = _TrackingSlot()
    observed_contexts: list[CancellationContext] = []

    async def typed_body(*_args: object, **_kwargs: object) -> object:
        return object()

    def fail_service(
        _value: object,
        *,
        cancellation: CancellationContext | None = None,
    ) -> None:
        assert cancellation is not None
        observed_contexts.append(cancellation)
        raise RuntimeError(_SENSITIVE)

    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)
    monkeypatch.setattr(adapter, "_typed_body", typed_body)
    monkeypatch.setattr(adapter, service_name, fail_service)
    endpoint = getattr(adapter, endpoint_name)

    with pytest.raises(HTTPException) as captured:
        asyncio.run(endpoint(cast("Request", _ConnectedRequest()), Response()))

    assert len(observed_contexts) == 1
    assert observed_contexts[0].deadline is not None
    assert captured.value.status_code == _HTTP_INTERNAL_ERROR
    assert captured.value.detail == expected_detail
    assert _SENSITIVE not in str(captured.value.detail)
    assert captured.value.headers == {"Cache-Control": "no-store"}
    assert slot.acquisitions == 1
    assert slot.releases == 1


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (ValueError(_SENSITIVE), _HTTP_UNPROCESSABLE),
        (KnccGbmFactorGraphProfileIntegrityError(_SENSITIVE), _HTTP_UNAVAILABLE),
        (KnccGbmFactorGraphInferenceError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
        (InferenceCancelledError(_SENSITIVE), _HTTP_CLIENT_CLOSED),
        (InferenceDeadlineExceededError(_SENSITIVE), _HTTP_TIMEOUT),
        (RuntimeError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
    ],
)
def test_analysis_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status: int,
) -> None:
    slot = _TrackingSlot()
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)
    monkeypatch.setattr(
        adapter,
        "analyze_kncc_gbm_factor_graph",
        partial(_raise_failure, failure),
    )
    with pytest.raises(HTTPException) as captured:
        adapter._execute(synthetic_demo_request())
    assert captured.value.status_code == status
    assert _SENSITIVE not in str(captured.value.detail)
    assert slot.released is True


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (ValueError(_SENSITIVE), _HTTP_UNPROCESSABLE),
        (KnccGbmFactorGraphProfileIntegrityError(_SENSITIVE), _HTTP_UNAVAILABLE),
        (KnccGbmFactorGraphReplayError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
        (InferenceCancelledError(_SENSITIVE), _HTTP_CLIENT_CLOSED),
        (InferenceDeadlineExceededError(_SENSITIVE), _HTTP_TIMEOUT),
        (RuntimeError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
    ],
)
def test_replay_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    real_receipt: Receipt,
    failure: Exception,
    status: int,
) -> None:
    request, result, _verification = real_receipt
    envelope = KnccGbmFactorGraphReplayVerificationRequest(request=request, result=result)
    slot = _TrackingSlot()
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)
    monkeypatch.setattr(
        adapter,
        "verify_kncc_gbm_factor_graph_replay",
        partial(_raise_failure, failure),
    )
    with pytest.raises(HTTPException) as captured:
        adapter._execute_verification(envelope)
    assert captured.value.status_code == status
    assert _SENSITIVE not in str(captured.value.detail)
    assert slot.released is True


def test_result_and_receipt_output_bounds(
    monkeypatch: pytest.MonkeyPatch,
    real_receipt: Receipt,
) -> None:
    request, result, verification = real_receipt
    envelope = KnccGbmFactorGraphReplayVerificationRequest(request=request, result=result)
    monkeypatch.setattr(adapter, "analyze_kncc_gbm_factor_graph", lambda *_a, **_k: result)
    with monkeypatch.context() as context:
        context.setattr(adapter, "GBM_FACTOR_GRAPH_RESULT_MAX_BYTES", 1)
        with pytest.raises(HTTPException) as result_bound:
            adapter._execute(request)
    assert result_bound.value.status_code == _HTTP_INTERNAL_ERROR
    with monkeypatch.context() as context:
        context.setattr(adapter, "GBM_FACTOR_GRAPH_REPLAY_MAX_BYTES", 1)
        with pytest.raises(HTTPException) as receipt_bound:
            adapter._execute(request)
    assert receipt_bound.value.status_code == _HTTP_INTERNAL_ERROR

    monkeypatch.setattr(
        adapter,
        "verify_kncc_gbm_factor_graph_replay",
        lambda *_a, **_k: verification,
    )
    with monkeypatch.context() as context:
        context.setattr(adapter, "GBM_FACTOR_GRAPH_RESULT_MAX_BYTES", 1)
        with pytest.raises(HTTPException) as verification_bound:
            adapter._execute_verification(envelope)
    assert verification_bound.value.status_code == _HTTP_INTERNAL_ERROR


def test_central_cli_group_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    real_receipt: Receipt,
) -> None:
    request, result, verification = real_receipt
    monkeypatch.setattr(adapter, "analyze_kncc_gbm_factor_graph", lambda *_a, **_k: result)
    monkeypatch.setattr(
        adapter,
        "verify_kncc_gbm_factor_graph_replay",
        lambda *_a, **_k: verification,
    )
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    profile = runner.invoke(cli_app, ["gbm-factor-graph", "profile"])
    demo = runner.invoke(cli_app, ["gbm-factor-graph", "demo"])
    analysis = runner.invoke(
        cli_app,
        ["gbm-factor-graph", "analyze", str(request_path)],
    )
    assert profile.exit_code == 0, profile.output
    assert demo.exit_code == 0, demo.output
    assert analysis.exit_code == 0, analysis.output

    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "request": request.model_dump(mode="json"),
                "result": json.loads(analysis.output),
            }
        ),
        encoding="utf-8",
    )
    replay = runner.invoke(
        cli_app,
        ["gbm-factor-graph", "verify", str(receipt_path)],
    )
    assert replay.exit_code == 0, replay.output
    assert json.loads(replay.output)["verified"] is True

    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        '{"analysis_id":"patient-a","analysis_id":"patient-b"}',
        encoding="utf-8",
    )
    rejected = runner.invoke(
        cli_app,
        ["gbm-factor-graph", "analyze", str(invalid)],
    )
    assert rejected.exit_code != 0
    assert "patient-" not in rejected.output

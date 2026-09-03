"""Fail-closed branch coverage for the narrow ECGI HTTP and CLI adapter."""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from glio_proteogen.adapters import research_state as adapter
from glio_proteogen.adapters.api import create_app
from glio_proteogen.research.proteogenomic_state import synthetic_demo_request
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
    checkpoint,
)
from glio_proteogen.research.proteogenomic_state.canonical import canonical_json_bytes

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.types import Message


class _ExhaustedSlots:
    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        return False

    def release(self) -> None:
        raise AssertionError("an unacquired slot must not be released")


def _raise_value_error(_value: object) -> Any:
    raise ValueError("private diagnostic must be sanitized")


def _asgi_request(
    messages: list[Message],
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    pending = list(messages)

    async def receive() -> Message:
        if pending:
            return pending.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "query_string": b"",
            "headers": headers or [],
        },
        receive,
    )


def _body_request(body: bytes) -> Request:
    return _asgi_request(
        [{"type": "http.request", "body": body, "more_body": False}],
        headers=[(b"content-type", b"application/json")],
    )


def test_cancellation_context_rejects_invalid_timeout_and_enforces_each_stop_state() -> None:
    with pytest.raises(ValueError, match="positive"):
        CancellationContext.with_timeout(0.0)

    unlimited = CancellationContext()
    assert unlimited.remaining_seconds() is None
    checkpoint(None)

    deadline = CancellationContext(deadline=1.0, clock=lambda: 2.0)
    assert deadline.remaining_seconds() == 0.0
    with pytest.raises(InferenceDeadlineExceededError, match="deadline"):
        deadline.checkpoint()

    cancelled = CancellationContext()
    cancelled.cancel()
    with pytest.raises(InferenceCancelledError, match="cancelled"):
        checkpoint(cancelled)


def test_adapter_readiness_and_error_schema_are_content_bound() -> None:
    assert adapter.ensure_research_state_ready().profile_digest.startswith("sha256:")
    response = adapter._error_response(
        "bounded",
        headers={"X-Test": {"schema": {"type": "string"}}},
    )
    assert response["headers"] == {"X-Test": {"schema": {"type": "string"}}}


def test_declared_content_length_rejects_non_numeric_and_negative_values() -> None:
    for raw in (b"invalid", b"-1"):
        request = _asgi_request([], headers=[(b"content-length", raw)])
        with pytest.raises(HTTPException) as captured:
            adapter._declared_content_length(request, 10)
        assert captured.value.status_code == 400
        assert captured.value.headers == {"Cache-Control": "no-store"}


def test_streaming_body_enforces_actual_bytes_and_maps_disconnects() -> None:
    oversized = _asgi_request([{"type": "http.request", "body": b"12345", "more_body": False}])
    with pytest.raises(HTTPException) as too_large:
        asyncio.run(adapter._bounded_body(oversized, 4))
    assert too_large.value.status_code == 413

    disconnected = _asgi_request([{"type": "http.disconnect"}])
    with pytest.raises(HTTPException) as cancelled:
        asyncio.run(adapter._bounded_body(disconnected, 4))
    assert cancelled.value.status_code == 499


def test_typed_body_maps_timeout_deadline_and_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = canonical_json_bytes(synthetic_demo_request().model_dump(mode="json"))

    async def time_out(_request: Request, _max_bytes: int) -> bytes:
        raise TimeoutError

    with monkeypatch.context() as scoped:
        scoped.setattr(adapter, "_bounded_body", time_out)
        with pytest.raises(HTTPException) as timed_out:
            asyncio.run(
                adapter._typed_body(
                    _body_request(body),
                    adapter._REQUEST_ADAPTER,
                    adapter.RESEARCH_STATE_REQUEST_MAX_BYTES,
                    CancellationContext(),
                )
            )
    assert timed_out.value.status_code == 504

    clock_values = iter((0.0, 2.0))
    deadline = CancellationContext(deadline=1.0, clock=lambda: next(clock_values))
    with pytest.raises(HTTPException) as expired:
        asyncio.run(
            adapter._typed_body(
                _body_request(body),
                adapter._REQUEST_ADAPTER,
                adapter.RESEARCH_STATE_REQUEST_MAX_BYTES,
                deadline,
            )
        )
    assert expired.value.status_code == 504

    cancelled_context = CancellationContext()
    cancelled_context.cancel()
    with pytest.raises(HTTPException) as cancelled:
        asyncio.run(
            adapter._typed_body(
                _body_request(body),
                adapter._REQUEST_ADAPTER,
                adapter.RESEARCH_STATE_REQUEST_MAX_BYTES,
                cancelled_context,
            )
        )
    assert cancelled.value.status_code == 499


def test_http_rejects_wrong_media_type_and_malformed_json(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        wrong_media = client.post(
            f"{adapter.RESEARCH_STATE_ROUTE_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        malformed = client.post(
            f"{adapter.RESEARCH_STATE_ROUTE_PREFIX}/analyze",
            content=b'{"sample_id":',
            headers={"content-type": "application/json"},
        )

    assert wrong_media.status_code == 415
    assert wrong_media.json() == {"detail": "content-type must be application/json"}
    assert malformed.status_code == 422
    assert malformed.json() == {"detail": "request does not satisfy the research-state contract"}


def test_analysis_and_replay_capacity_gates_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", _ExhaustedSlots())
    request = synthetic_demo_request()

    with pytest.raises(HTTPException, match="capacity") as analysis_error:
        adapter._execute(request)
    with pytest.raises(HTTPException, match="capacity") as replay_error:
        adapter._execute_verification(object())  # type: ignore[arg-type]

    assert analysis_error.value.status_code == 429
    assert replay_error.value.status_code == 429


def test_execute_sanitizes_engine_errors_and_enforces_result_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    monkeypatch.setattr(adapter, "analyze_proteogenomic_state", _raise_value_error)
    with pytest.raises(HTTPException, match="could not be evaluated") as analysis_error:
        adapter._execute(request)
    assert analysis_error.value.status_code == 422

    monkeypatch.setattr(adapter, "analyze_proteogenomic_state", lambda _request: object())
    monkeypatch.setattr(
        adapter,
        "canonical_json_bytes",
        lambda _value: b"x" * (adapter.RESEARCH_STATE_RESULT_MAX_BYTES + 1),
    )
    with pytest.raises(HTTPException, match="transport bound") as size_error:
        adapter._execute(request)
    assert size_error.value.status_code == 500


def test_execute_verification_sanitizes_engine_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapter, "verify_proteogenomic_replay", _raise_value_error)
    with pytest.raises(HTTPException, match="replay envelope") as replay_error:
        adapter._execute_verification(object())  # type: ignore[arg-type]
    assert replay_error.value.status_code == 422


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (InferenceDeadlineExceededError("private deadline"), 504),
        (InferenceCancelledError("private cancellation"), 499),
    ],
)
def test_execute_maps_cooperative_analysis_stops(
    failure: Exception,
    expected_status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stop(_request: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(adapter, "analyze_proteogenomic_state", stop)
    with pytest.raises(HTTPException) as captured:
        adapter._execute(synthetic_demo_request(), CancellationContext())
    assert captured.value.status_code == expected_status
    assert "private" not in str(captured.value.detail)


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (InferenceDeadlineExceededError("private deadline"), 504),
        (InferenceCancelledError("private cancellation"), 499),
    ],
)
def test_execute_verification_maps_cooperative_stops(
    failure: Exception,
    expected_status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stop(_request: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(adapter, "verify_proteogenomic_replay", stop)
    with pytest.raises(HTTPException) as captured:
        adapter._execute_verification(object(), CancellationContext())  # type: ignore[arg-type]
    assert captured.value.status_code == expected_status
    assert "private" not in str(captured.value.detail)


def test_execute_enforces_complete_receipt_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    request = synthetic_demo_request()
    result = adapter.analyze_proteogenomic_state(request)
    monkeypatch.setattr(adapter, "analyze_proteogenomic_state", lambda _request: result)

    def encode(value: object) -> bytes:
        if isinstance(value, dict):
            return b"x" * (adapter.RESEARCH_STATE_REPLAY_MAX_BYTES + 1)
        return b"{}"

    monkeypatch.setattr(adapter, "canonical_json_bytes", encode)
    with pytest.raises(HTTPException, match="replay bound") as captured:
        adapter._execute(request)
    assert captured.value.status_code == 500


def test_disconnect_watcher_cancels_context() -> None:
    async def exercise() -> CancellationContext:
        cancellation = CancellationContext()
        await adapter._watch_disconnect(
            _asgi_request([{"type": "http.disconnect"}]),
            cancellation,
            asyncio.Event(),
        )
        return cancellation

    cancellation = asyncio.run(exercise())
    with pytest.raises(InferenceCancelledError):
        cancellation.checkpoint()


def test_cli_file_and_engine_failures_are_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_bytes(b'{"duplicate":1,"duplicate":2}')
    with pytest.raises(adapter.ResearchStateCliError, match="does not satisfy"):
        adapter._read_typed(
            invalid_path,
            adapter._REQUEST_ADAPTER,
            adapter.RESEARCH_STATE_REQUEST_MAX_BYTES,
        )

    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(synthetic_demo_request().model_dump(mode="json")))
    with monkeypatch.context() as scoped:
        scoped.setattr(adapter, "analyze_proteogenomic_state", _raise_value_error)
        with pytest.raises(adapter.ResearchStateCliError, match="analysis failed safely"):
            adapter.cli_analyze(request_path)

    with monkeypatch.context() as scoped:
        scoped.setattr(adapter, "analyze_proteogenomic_state", lambda _request: object())
        scoped.setattr(
            adapter,
            "canonical_json_bytes",
            lambda _value: b"x" * (adapter.RESEARCH_STATE_RESULT_MAX_BYTES + 1),
        )
        with pytest.raises(adapter.ResearchStateCliError, match="analysis failed safely"):
            adapter.cli_analyze(request_path)

    with monkeypatch.context() as scoped:
        scoped.setattr(adapter, "_read_typed", lambda *_args: object())
        scoped.setattr(adapter, "verify_proteogenomic_replay", _raise_value_error)
        with pytest.raises(adapter.ResearchStateCliError, match="replay failed safely"):
            adapter.cli_verify(tmp_path / "unused.json")


def test_bare_research_router_enforces_admission_headers_and_openapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    app.include_router(adapter.router)
    adapter.install_research_state_openapi(app)
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", _ExhaustedSlots())
    monkeypatch.setattr(
        adapter,
        "_decode_typed",
        lambda *_args: pytest.fail("capacity must be acquired before request parsing"),
    )

    with TestClient(app) as client:
        response = client.post(
            f"{adapter.RESEARCH_STATE_ROUTE_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "application/json"},
        )
        openapi = client.get("/openapi.json").json()

    assert response.status_code == 429
    assert response.headers["retry-after"] == str(adapter.RESEARCH_STATE_RETRY_AFTER_SECONDS)
    assert response.headers["cache-control"] == "no-store"
    responses = openapi["paths"][f"{adapter.RESEARCH_STATE_ROUTE_PREFIX}/analyze"]["post"][
        "responses"
    ]
    assert set(responses) == {"200", "400", "413", "415", "422", "429", "499", "500", "504"}


def test_bare_research_router_rejects_oversize_before_json_parsing() -> None:
    app = FastAPI()
    app.include_router(adapter.router)
    body = b"{}" + b" " * (adapter.RESEARCH_STATE_REQUEST_MAX_BYTES - 1)

    with TestClient(app) as client:
        response = client.post(
            f"{adapter.RESEARCH_STATE_ROUTE_PREFIX}/analyze",
            content=body,
            headers={"content-type": "application/json"},
        )

    assert len(body) == adapter.RESEARCH_STATE_REQUEST_MAX_BYTES + 1
    assert response.status_code == 413
    assert response.json() == {"detail": "request body exceeds the byte limit"}
    assert response.headers["cache-control"] == "no-store"

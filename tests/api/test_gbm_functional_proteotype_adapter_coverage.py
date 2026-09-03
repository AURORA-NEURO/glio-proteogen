"""Adversarial branch coverage for the functional-proteotype HTTP/CLI adapter."""

from __future__ import annotations

import asyncio
import sys
from io import StringIO
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
import typer
from fastapi import HTTPException, Response
from pydantic import TypeAdapter
from starlette.requests import Request

from glio_proteogen.adapters import gbm_functional_proteotype as adapter
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.types import Message, Scope

    from glio_proteogen.research.gbm_functional_proteotype.contracts import (
        FunctionalProteotypeRequest,
        ReplayVerificationRequest,
    )

_SENSITIVE = "private-patient-diagnostic"
_HTTP_BAD_REQUEST = 400
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_UNPROCESSABLE = 422
_HTTP_CLIENT_CLOSED = 499
_HTTP_INTERNAL_ERROR = 500
_HTTP_TIMEOUT = 504
_EXPECTED_DISCONNECT_POLLS = 2


class _CheckpointFailure:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure

    def remaining_seconds(self) -> None:
        return None

    def checkpoint(self) -> None:
        raise self.failure


class _TrackingSlots:
    def __init__(self) -> None:
        self.acquisitions = 0
        self.releases = 0

    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        self.acquisitions += 1
        return True

    def release(self) -> None:
        self.releases += 1


class _DisconnectAfterOnePoll:
    def __init__(self) -> None:
        self.polls = 0

    async def is_disconnected(self) -> bool:
        self.polls += 1
        return self.polls > 1


def _stream_request(
    *bodies: bytes,
    headers: tuple[tuple[bytes, bytes], ...] = ((b"content-type", b"application/json"),),
    disconnect: bool = False,
) -> Request:
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
            "path": adapter.GBM_FUNCTIONAL_PROTEOTYPE_ROUTE_PREFIX,
            "headers": list(headers),
        },
    )
    return Request(scope, receive)


def _raise_failure(failure: Exception, *_args: object, **_kwargs: object) -> Any:
    raise failure


def _assert_http_error(error: HTTPException, status: int) -> None:
    assert error.status_code == status
    assert _SENSITIVE not in str(error.detail)
    assert error.headers == {"Cache-Control": "no-store"}


def test_bounded_body_validates_metadata_stream_size_and_disconnect() -> None:
    assert asyncio.run(adapter._bounded_body(_stream_request(b"ab", b"cd"), 4)) == b"abcd"

    for raw_length, maximum, expected_status in (
        (b"not-an-integer", 4, _HTTP_BAD_REQUEST),
        (b"-1", 4, _HTTP_BAD_REQUEST),
        (b"5", 4, _HTTP_PAYLOAD_TOO_LARGE),
    ):
        request = _stream_request(
            b"body is never consumed",
            headers=((b"content-length", raw_length),),
        )
        with pytest.raises(HTTPException) as captured:
            asyncio.run(adapter._bounded_body(request, maximum))
        assert captured.value.status_code == expected_status
        assert captured.value.headers == {"Cache-Control": "no-store"}

    with pytest.raises(HTTPException) as streamed:
        asyncio.run(adapter._bounded_body(_stream_request(b"ab", b"cd"), 3))
    assert streamed.value.status_code == _HTTP_PAYLOAD_TOO_LARGE

    with pytest.raises(HTTPException) as disconnected:
        asyncio.run(adapter._bounded_body(_stream_request(disconnect=True), 3))
    assert disconnected.value.status_code == _HTTP_CLIENT_CLOSED


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (InferenceDeadlineExceededError(_SENSITIVE), _HTTP_TIMEOUT),
        (InferenceCancelledError(_SENSITIVE), _HTTP_CLIENT_CLOSED),
    ],
)
def test_typed_body_maps_cooperative_checkpoint_failures(
    failure: Exception,
    expected_status: int,
) -> None:
    cancellation = cast("CancellationContext", _CheckpointFailure(failure))
    with pytest.raises(HTTPException) as captured:
        asyncio.run(
            adapter._typed_body(
                _stream_request(b"{}"),
                TypeAdapter(dict[str, int]),
                64,
                cancellation,
            )
        )
    _assert_http_error(captured.value, expected_status)


def test_typed_body_maps_timeout_and_strict_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def timeout(_request: Request, _maximum: int) -> bytes:
        raise TimeoutError(_SENSITIVE)

    with monkeypatch.context() as context:
        context.setattr(adapter, "_bounded_body", timeout)
        with pytest.raises(HTTPException) as captured:
            asyncio.run(
                adapter._typed_body(
                    _stream_request(b"{}"),
                    TypeAdapter(dict[str, int]),
                    64,
                    CancellationContext(),
                )
            )
    _assert_http_error(captured.value, _HTTP_TIMEOUT)

    for invalid in (b'{"duplicate":1,"duplicate":2}', b'{"value":"not-an-integer"}'):
        with pytest.raises(HTTPException) as invalid_body:
            asyncio.run(
                adapter._typed_body(
                    _stream_request(invalid),
                    TypeAdapter(dict[str, int]),
                    64,
                    CancellationContext(),
                )
            )
        _assert_http_error(invalid_body.value, _HTTP_UNPROCESSABLE)


def test_disconnect_watcher_polls_then_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _DisconnectAfterOnePoll()
    cancellation = CancellationContext()
    monkeypatch.setattr(adapter, "_DISCONNECT_POLL_SECONDS", 0.0)
    asyncio.run(
        adapter._watch_disconnect(
            cast("Request", request),
            cancellation,
            asyncio.Event(),
        )
    )
    assert request.polls == _EXPECTED_DISCONNECT_POLLS
    with pytest.raises(InferenceCancelledError):
        cancellation.checkpoint()


def test_execute_enforces_result_and_replay_receipt_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = cast("FunctionalProteotypeRequest", object())
    result = object()

    with monkeypatch.context() as context:
        context.setattr(adapter, "analyze_functional_proteotype", lambda *_args, **_kwargs: result)
        context.setattr(adapter, "canonical_json_bytes", lambda _value: b"xx")
        context.setattr(adapter, "GBM_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES", 1)
        with pytest.raises(HTTPException) as result_bound:
            adapter._execute(request, CancellationContext())
    _assert_http_error(result_bound.value, _HTTP_INTERNAL_ERROR)
    assert result_bound.value.detail == "functional-proteotype result exceeded its bound"

    with monkeypatch.context() as context:
        context.setattr(adapter, "analyze_functional_proteotype", lambda *_args, **_kwargs: result)
        context.setattr(
            adapter,
            "canonical_json_bytes",
            lambda value: b"x" if value is result else b"xx",
        )
        context.setattr(adapter, "GBM_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES", 1)
        context.setattr(adapter, "GBM_FUNCTIONAL_PROTEOTYPE_REPLAY_MAX_BYTES", 1)
        with pytest.raises(HTTPException) as receipt_bound:
            adapter._execute(request, CancellationContext())
    _assert_http_error(receipt_bound.value, _HTTP_INTERNAL_ERROR)
    assert receipt_bound.value.detail == "functional-proteotype receipt exceeded its bound"


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (InferenceDeadlineExceededError(_SENSITIVE), _HTTP_TIMEOUT),
        (InferenceCancelledError(_SENSITIVE), _HTTP_CLIENT_CLOSED),
        (ValueError(_SENSITIVE), _HTTP_UNPROCESSABLE),
        (RuntimeError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
    ],
)
def test_verification_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_status: int,
) -> None:
    envelope = cast("ReplayVerificationRequest", object())
    monkeypatch.setattr(
        adapter,
        "verify_replay",
        lambda *_args, **_kwargs: _raise_failure(failure),
    )
    with pytest.raises(HTTPException) as captured:
        adapter._execute_verification(envelope, CancellationContext())
    _assert_http_error(captured.value, expected_status)


def test_verification_result_bound_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope = cast("ReplayVerificationRequest", object())
    monkeypatch.setattr(adapter, "verify_replay", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(adapter, "canonical_json_bytes", lambda _value: b"xx")
    monkeypatch.setattr(adapter, "GBM_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES", 1)
    with pytest.raises(HTTPException) as captured:
        adapter._execute_verification(envelope, CancellationContext())
    _assert_http_error(captured.value, _HTTP_INTERNAL_ERROR)
    assert captured.value.detail == "functional-proteotype verification exceeded its bound"


@pytest.mark.parametrize(
    ("endpoint_name", "dependency_name"),
    [("profile", "algorithm_profile"), ("demo", "synthetic_demo_request")],
)
def test_read_endpoints_sanitize_profile_and_demo_failures(
    monkeypatch: pytest.MonkeyPatch,
    endpoint_name: str,
    dependency_name: str,
) -> None:
    monkeypatch.setattr(
        adapter,
        dependency_name,
        lambda: _raise_failure(RuntimeError(_SENSITIVE)),
    )
    with pytest.raises(HTTPException) as captured:
        getattr(adapter, endpoint_name)(Response())
    _assert_http_error(captured.value, _HTTP_INTERNAL_ERROR)


@pytest.mark.parametrize("endpoint_name", ["analyze", "verify"])
def test_routes_release_slot_when_watcher_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
    endpoint_name: str,
) -> None:
    slots = _TrackingSlots()

    async def typed_body(*_args: object, **_kwargs: object) -> object:
        return object()

    def reject_watcher(coroutine: Any) -> None:
        coroutine.close()
        raise RuntimeError(_SENSITIVE)

    monkeypatch.setattr(adapter, "_typed_body", typed_body)
    monkeypatch.setattr(adapter, "_SLOTS", slots)
    monkeypatch.setattr(asyncio, "create_task", reject_watcher)
    endpoint = getattr(adapter, endpoint_name)
    with pytest.raises(RuntimeError, match=_SENSITIVE):
        asyncio.run(endpoint(cast("Request", object()), Response()))
    assert slots.acquisitions == 1
    assert slots.releases == 1


def test_cli_reader_sanitizes_io_size_json_and_model_errors(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(b'{"key":1,"key":2}')
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"xx")
    wrong_shape = tmp_path / "wrong-shape.json"
    wrong_shape.write_bytes(b"[]")

    for path, maximum in (
        (tmp_path / "missing.json", 64),
        (duplicate, 64),
        (oversized, 1),
        (wrong_shape, 64),
    ):
        with pytest.raises(adapter.GbmFunctionalProteotypeCliError) as captured:
            adapter._read_typed(path, TypeAdapter(dict[str, int]), maximum)
        assert str(captured.value) == adapter._CLI_INPUT_ERROR


def test_emit_falls_back_to_a_text_only_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    adapter._emit({"axis": "GBM-δ"})
    assert stream.getvalue() == '{"axis":"GBM-δ"}\n\n'


@pytest.mark.parametrize(
    ("command_name", "dependency_name"),
    [("cli_profile", "algorithm_profile"), ("cli_demo", "synthetic_demo_request")],
)
def test_cli_read_commands_sanitize_failures(
    monkeypatch: pytest.MonkeyPatch,
    command_name: str,
    dependency_name: str,
) -> None:
    monkeypatch.setattr(
        adapter,
        dependency_name,
        lambda: _raise_failure(RuntimeError(_SENSITIVE)),
    )
    with pytest.raises(adapter.GbmFunctionalProteotypeCliError) as captured:
        getattr(adapter, command_name)()
    assert str(captured.value) == adapter._CLI_ANALYSIS_ERROR
    assert _SENSITIVE not in str(captured.value)


@pytest.mark.parametrize(
    ("command_name", "dependency_name", "expected_error"),
    [
        ("cli_analyze", "analyze_functional_proteotype", adapter._CLI_ANALYSIS_ERROR),
        ("cli_verify", "verify_replay", adapter._CLI_REPLAY_ERROR),
    ],
)
def test_cli_compute_commands_sanitize_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command_name: str,
    dependency_name: str,
    expected_error: str,
) -> None:
    monkeypatch.setattr(adapter, "_read_typed", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        adapter,
        dependency_name,
        lambda *_args, **_kwargs: _raise_failure(RuntimeError(_SENSITIVE)),
    )
    with pytest.raises(adapter.GbmFunctionalProteotypeCliError) as captured:
        getattr(adapter, command_name)(tmp_path / "unused.json")
    assert str(captured.value) == expected_error
    assert _SENSITIVE not in str(captured.value)


def test_cli_analyze_enforces_result_bound(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(adapter, "_read_typed", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(adapter, "analyze_functional_proteotype", lambda _request: object())
    monkeypatch.setattr(adapter, "canonical_json_bytes", lambda _value: b"xx")
    monkeypatch.setattr(adapter, "GBM_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES", 1)
    with pytest.raises(adapter.GbmFunctionalProteotypeCliError) as captured:
        adapter.cli_analyze(tmp_path / "unused.json")
    assert str(captured.value) == adapter._CLI_RESULT_SIZE_ERROR


def test_cli_verify_emits_failed_verification_then_exits_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = SimpleNamespace(verified=False)
    emitted: list[object] = []
    monkeypatch.setattr(adapter, "_read_typed", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(adapter, "verify_replay", lambda _envelope: result)
    monkeypatch.setattr(adapter, "_emit", emitted.append)
    with pytest.raises(typer.Exit) as captured:
        adapter.cli_verify(tmp_path / "unused.json")
    assert captured.value.exit_code == 1
    assert emitted == [result]

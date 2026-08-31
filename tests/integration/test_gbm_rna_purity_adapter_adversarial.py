"""Adversarial HTTP and CLI boundary coverage for the GBMPurity lane."""

from __future__ import annotations

import asyncio
import json
import sys
from io import StringIO
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
import typer
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from starlette.requests import Request
from typer.testing import CliRunner

from glio_proteogen.adapters import gbm_rna_purity as adapter
from glio_proteogen.adapters.cli import app as root_cli
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.gbm_rna_purity.canonical import sha256_digest
from glio_proteogen.research.gbm_rna_purity.contracts import (
    REQUIRED_CONTEXT,
    GbmRnaPurityReplayVerificationRequest,
    GbmRnaPurityRequest,
    RawGeneCount,
)
from glio_proteogen.research.gbm_rna_purity.service import analyze_gbm_rna_purity
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.types import Message, Scope

_SENSITIVE = "private-patient-diagnostic"
_HTTP_BAD_REQUEST = 400
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_MEDIA_TYPE = 415
_HTTP_UNPROCESSABLE = 422
_HTTP_TOO_MANY_REQUESTS = 429
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
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.acquisitions = 0
        self.releases = 0

    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        self.acquisitions += 1
        return self.available

    def release(self) -> None:
        self.releases += 1


class _DisconnectAfterOnePoll:
    def __init__(self) -> None:
        self.polls = 0

    async def is_disconnected(self) -> bool:
        self.polls += 1
        return self.polls > 1


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(adapter.router)
    adapter.install_gbm_rna_purity_openapi(app)
    return app


def _small_request() -> GbmRnaPurityRequest:
    return GbmRnaPurityRequest(
        sample_id="adapter.adversarial",
        context=REQUIRED_CONTEXT,
        counts_provenance_digest=sha256_digest({"adapter": "adversarial"}),
        counts=(RawGeneCount(gene_symbol="EGFR", raw_count=100.0),),
    )


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
            "path": f"{adapter.GBM_RNA_PURITY_ROUTE_PREFIX}/analyze",
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


def test_bounded_body_validates_length_stream_and_disconnect() -> None:
    assert asyncio.run(adapter._bounded_body(_stream_request(b"ab", b"cd"), 4)) == b"abcd"
    for raw_length, maximum, expected_status in (
        (b"not-an-integer", 4, _HTTP_BAD_REQUEST),
        (b"-1", 4, _HTTP_BAD_REQUEST),
        (b"5", 4, _HTTP_PAYLOAD_TOO_LARGE),
    ):
        request = _stream_request(
            b"unread",
            headers=((b"content-length", raw_length),),
        )
        with pytest.raises(HTTPException) as captured:
            asyncio.run(adapter._bounded_body(request, maximum))
        _assert_http_error(captured.value, expected_status)

    with pytest.raises(HTTPException) as streamed:
        asyncio.run(adapter._bounded_body(_stream_request(b"ab", b"cd"), 3))
    _assert_http_error(streamed.value, _HTTP_PAYLOAD_TOO_LARGE)

    with pytest.raises(HTTPException) as disconnected:
        asyncio.run(adapter._bounded_body(_stream_request(disconnect=True), 3))
    _assert_http_error(disconnected.value, _HTTP_CLIENT_CLOSED)


def test_typed_body_requires_json_and_rejects_ambiguous_or_invalid_json() -> None:
    with pytest.raises(HTTPException) as media:
        asyncio.run(
            adapter._typed_body(
                _stream_request(b"{}", headers=((b"content-type", b"text/plain"),)),
                TypeAdapter(dict[str, int]),
                64,
                CancellationContext(),
            )
        )
    _assert_http_error(media.value, _HTTP_MEDIA_TYPE)

    for invalid in (b'{"key":1,"key":2}', b'{"key":"wrong"}', b"[]"):
        with pytest.raises(HTTPException) as captured:
            asyncio.run(
                adapter._typed_body(
                    _stream_request(invalid),
                    TypeAdapter(dict[str, int]),
                    64,
                    CancellationContext(),
                )
            )
        _assert_http_error(captured.value, _HTTP_UNPROCESSABLE)


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


def test_typed_body_maps_transport_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def timeout(_request: Request, _maximum: int) -> bytes:
        raise TimeoutError(_SENSITIVE)

    monkeypatch.setattr(adapter, "_bounded_body", timeout)
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


def test_disconnect_watcher_cancels_cooperative_context(
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


def test_capacity_failure_has_retry_header_and_does_not_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = _TrackingSlots(available=False)
    monkeypatch.setattr(adapter, "_SLOTS", slots)
    with pytest.raises(HTTPException) as captured:
        adapter._acquire_slot()
    assert captured.value.status_code == _HTTP_TOO_MANY_REQUESTS
    assert captured.value.headers == {"Cache-Control": "no-store", "Retry-After": "1"}
    assert slots.acquisitions == 1
    assert slots.releases == 0


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (InferenceDeadlineExceededError(_SENSITIVE), _HTTP_TIMEOUT),
        (InferenceCancelledError(_SENSITIVE), _HTTP_CLIENT_CLOSED),
        (ValueError(_SENSITIVE), _HTTP_UNPROCESSABLE),
        (RuntimeError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
    ],
)
def test_execute_sanitizes_all_engine_failure_families(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_status: int,
) -> None:
    monkeypatch.setattr(
        adapter,
        "analyze_gbm_rna_purity",
        lambda *_args, **_kwargs: _raise_failure(failure),
    )
    with pytest.raises(HTTPException) as captured:
        adapter._execute(_small_request(), CancellationContext())
    _assert_http_error(captured.value, expected_status)


def test_execute_enforces_result_and_receipt_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _small_request()
    result = object()
    with monkeypatch.context() as context:
        context.setattr(adapter, "analyze_gbm_rna_purity", lambda *_args, **_kwargs: result)
        context.setattr(adapter, "canonical_json_bytes", lambda _value: b"xx")
        context.setattr(adapter, "GBM_RNA_PURITY_RESULT_MAX_BYTES", 1)
        with pytest.raises(HTTPException) as captured:
            adapter._execute(request, CancellationContext())
    _assert_http_error(captured.value, _HTTP_INTERNAL_ERROR)
    assert captured.value.detail == "GBM RNA purity result exceeded its bound"

    with monkeypatch.context() as context:
        context.setattr(adapter, "analyze_gbm_rna_purity", lambda *_args, **_kwargs: result)
        context.setattr(
            adapter,
            "canonical_json_bytes",
            lambda value: b"x" if value is result else b"xx",
        )
        context.setattr(adapter, "GBM_RNA_PURITY_RESULT_MAX_BYTES", 1)
        context.setattr(adapter, "GBM_RNA_PURITY_REPLAY_MAX_BYTES", 1)
        with pytest.raises(HTTPException) as receipt:
            adapter._execute(request, CancellationContext())
    _assert_http_error(receipt.value, _HTTP_INTERNAL_ERROR)
    assert receipt.value.detail == "GBM RNA purity receipt exceeded its bound"


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (InferenceDeadlineExceededError(_SENSITIVE), _HTTP_TIMEOUT),
        (InferenceCancelledError(_SENSITIVE), _HTTP_CLIENT_CLOSED),
        (ValueError(_SENSITIVE), _HTTP_UNPROCESSABLE),
        (RuntimeError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
    ],
)
def test_verification_sanitizes_all_failure_families(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_status: int,
) -> None:
    envelope = GbmRnaPurityReplayVerificationRequest(
        request=_small_request(),
        result=analyze_gbm_rna_purity(_small_request()),
    )
    monkeypatch.setattr(
        adapter,
        "verify_gbm_rna_purity_replay",
        lambda *_args, **_kwargs: _raise_failure(failure),
    )
    with pytest.raises(HTTPException) as captured:
        adapter._execute_verification(envelope, CancellationContext())
    _assert_http_error(captured.value, expected_status)


def test_verification_result_bound_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope = cast("GbmRnaPurityReplayVerificationRequest", object())
    monkeypatch.setattr(adapter, "verify_gbm_rna_purity_replay", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(adapter, "canonical_json_bytes", lambda _value: b"xx")
    monkeypatch.setattr(adapter, "GBM_RNA_PURITY_RESULT_MAX_BYTES", 1)
    with pytest.raises(HTTPException) as captured:
        adapter._execute_verification(envelope, CancellationContext())
    _assert_http_error(captured.value, _HTTP_INTERNAL_ERROR)
    assert captured.value.detail == "GBM RNA purity verification exceeded its bound"


@pytest.mark.parametrize(
    ("endpoint_name", "dependency_name"),
    [("profile", "algorithm_profile"), ("demo", "synthetic_demo_request")],
)
def test_read_endpoints_sanitize_integrity_failures(
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
def test_routes_release_capacity_when_watcher_creation_fails(
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


def test_http_capacity_and_internal_failure_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _small_request()
    result = analyze_gbm_rna_purity(request)
    envelope = GbmRnaPurityReplayVerificationRequest(request=request, result=result)
    with TestClient(_app()) as client:
        monkeypatch.setattr(adapter, "_SLOTS", _TrackingSlots(available=False))
        unavailable = client.post(
            f"{adapter.GBM_RNA_PURITY_ROUTE_PREFIX}/analyze",
            content=request.model_dump_json(),
            headers={"content-type": "application/json"},
        )
        unavailable_verify = client.post(
            f"{adapter.GBM_RNA_PURITY_ROUTE_PREFIX}/verify",
            content=envelope.model_dump_json(),
            headers={"content-type": "application/json"},
        )
        monkeypatch.setattr(adapter, "_SLOTS", _TrackingSlots())
        monkeypatch.setattr(
            adapter,
            "analyze_gbm_rna_purity",
            lambda *_args, **_kwargs: _raise_failure(RuntimeError(_SENSITIVE)),
        )
        failed = client.post(
            f"{adapter.GBM_RNA_PURITY_ROUTE_PREFIX}/analyze",
            content=request.model_dump_json(),
            headers={"content-type": "application/json"},
        )

    assert unavailable.status_code == _HTTP_TOO_MANY_REQUESTS
    assert unavailable.headers["retry-after"] == "1"
    assert unavailable_verify.status_code == _HTTP_TOO_MANY_REQUESTS
    assert failed.status_code == _HTTP_INTERNAL_ERROR
    assert _SENSITIVE not in failed.text


def test_openapi_is_idempotent_and_declares_exact_bounded_contracts() -> None:
    app = _app()
    adapter.install_gbm_rna_purity_openapi(app)
    left = app.openapi()
    right = app.openapi()
    assert left == right
    prefix = adapter.GBM_RNA_PURITY_ROUTE_PREFIX
    analyze = left["paths"][f"{prefix}/analyze"]["post"]
    verify = left["paths"][f"{prefix}/verify"]["post"]
    assert analyze["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GbmRnaPurityRequest"
    }
    assert verify["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GbmRnaPurityReplayVerificationRequest"
    }
    assert set(analyze["responses"]) >= {
        "200",
        "400",
        "413",
        "415",
        "422",
        "429",
        "499",
        "500",
        "504",
    }


def test_cli_profile_demo_analyze_verify_lifecycle(tmp_path: Path) -> None:
    runner = CliRunner()
    profile = runner.invoke(root_cli, ["gbm-rna-purity", "profile"])
    demo = runner.invoke(root_cli, ["gbm-rna-purity", "demo"])
    assert profile.exit_code == 0, profile.output
    assert demo.exit_code == 0, demo.output
    request_path = tmp_path / "request.json"
    request_path.write_text(demo.stdout, encoding="utf-8")
    analysis = runner.invoke(root_cli, ["gbm-rna-purity", "analyze", str(request_path)])
    assert analysis.exit_code == 0, analysis.output
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_bytes(
        canonical_json_bytes(
            {"request": json.loads(demo.stdout), "result": json.loads(analysis.stdout)}
        )
    )
    verification = runner.invoke(root_cli, ["gbm-rna-purity", "verify", str(envelope_path)])
    assert verification.exit_code == 0, verification.output
    assert json.loads(verification.stdout)["verified"] is True


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
        with pytest.raises(adapter.GbmRnaPurityCliError) as captured:
            adapter._read_typed(path, TypeAdapter(dict[str, int]), maximum)
        assert str(captured.value) == adapter._CLI_INPUT_ERROR


def test_emit_falls_back_to_text_only_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    adapter._emit({"context": "GBM-δ"})
    assert stream.getvalue() == '{"context":"GBM-δ"}\n\n'


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
    with pytest.raises(adapter.GbmRnaPurityCliError) as captured:
        getattr(adapter, command_name)()
    assert str(captured.value) == adapter._CLI_ANALYSIS_ERROR
    assert _SENSITIVE not in str(captured.value)


@pytest.mark.parametrize(
    ("command_name", "dependency_name", "expected_error"),
    [
        ("cli_analyze", "analyze_gbm_rna_purity", adapter._CLI_ANALYSIS_ERROR),
        ("cli_verify", "verify_gbm_rna_purity_replay", adapter._CLI_REPLAY_ERROR),
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
    with pytest.raises(adapter.GbmRnaPurityCliError) as captured:
        getattr(adapter, command_name)(tmp_path / "unused.json")
    assert str(captured.value) == expected_error
    assert _SENSITIVE not in str(captured.value)


def test_cli_analyze_enforces_result_bound(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(adapter, "_read_typed", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(adapter, "analyze_gbm_rna_purity", lambda _request: object())
    monkeypatch.setattr(adapter, "canonical_json_bytes", lambda _value: b"xx")
    monkeypatch.setattr(adapter, "GBM_RNA_PURITY_RESULT_MAX_BYTES", 1)
    with pytest.raises(adapter.GbmRnaPurityCliError) as captured:
        adapter.cli_analyze(tmp_path / "unused.json")
    assert str(captured.value) == adapter._CLI_RESULT_SIZE_ERROR


def test_cli_verify_emits_mismatch_then_exits_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = SimpleNamespace(verified=False)
    emitted: list[object] = []
    monkeypatch.setattr(adapter, "_read_typed", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(adapter, "verify_gbm_rna_purity_replay", lambda _envelope: result)
    monkeypatch.setattr(adapter, "_emit", emitted.append)
    with pytest.raises(typer.Exit) as captured:
        adapter.cli_verify(tmp_path / "unused.json")
    assert captured.value.exit_code == 1
    assert emitted == [result]

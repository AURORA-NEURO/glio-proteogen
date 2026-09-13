"""HTTP/CLI lifecycle and hard guards for Reactome conditional transitions."""

from __future__ import annotations

import asyncio
import json
from functools import partial
from io import StringIO
from typing import TYPE_CHECKING, cast

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from typer.testing import CliRunner

from glio_proteogen.adapters import longitudinal_gbm_reactome_transition as adapter
from glio_proteogen.adapters.api import create_app
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    ALGORITHM_PROFILE_ID,
    LongitudinalGbmReactomeTransitionRequest,
    LongitudinalGbmReactomeTransitionResult,
    ReactomeConditionalReplayVerificationRequest,
    ReactomeConditionalReplayVerificationResult,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.demo import (
    DEMO_ID,
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.errors import (
    ReactomeConditionalInferenceError,
    ReactomeConditionalModelIntegrityError,
    ReactomeTransitionSourceIntegrityError,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.service import (
    analyze_longitudinal_gbm_reactome_transition,
    verify_longitudinal_gbm_reactome_transition_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.types import Message, Scope

_PREFIX = adapter.LONGITUDINAL_GBM_REACTOME_TRANSITION_ROUTE_PREFIX
_MEBIBYTE = 1_024 * 1_024
_SENSITIVE = "patient-sensitive-canary"
_HTTP_OK = 200
_HTTP_BAD_REQUEST = 400
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_UNSUPPORTED_MEDIA = 415
_HTTP_UNPROCESSABLE = 422
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_CLIENT_CLOSED = 499
_HTTP_INTERNAL_ERROR = 500
_HTTP_UNAVAILABLE = 503
_HTTP_TIMEOUT = 504
_EXPECTED_CONCURRENCY = 2
_EXPECTED_TIMEOUT_SECONDS = 120.0
_EXPECTED_TRANSITIONS = 3
_UNAVAILABLE_RELEASE_MESSAGE = "an unavailable slot cannot be released"

Receipt = tuple[
    LongitudinalGbmReactomeTransitionRequest,
    LongitudinalGbmReactomeTransitionResult,
    ReactomeConditionalReplayVerificationResult,
]


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


class _CheckpointFailure:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure

    def remaining_seconds(self) -> None:
        return None

    def checkpoint(self) -> None:
        raise self.failure


def _raise_failure(failure: Exception, *_args: object, **_kwargs: object) -> None:
    raise failure


@pytest.fixture(scope="module")
def real_receipt() -> Receipt:
    request = synthetic_demo_request()
    result = analyze_longitudinal_gbm_reactome_transition(request)
    verification = verify_longitudinal_gbm_reactome_transition_replay(
        ReactomeConditionalReplayVerificationRequest(request=request, result=result)
    )
    assert verification.verified is True
    return request, result, verification


def _app() -> FastAPI:
    app = FastAPI()
    adapter.mount_longitudinal_gbm_reactome_transition(app)
    adapter.install_longitudinal_gbm_reactome_transition_openapi(app)
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


def test_exact_limits_and_real_service_receipt(real_receipt: Receipt) -> None:
    request, result, verification = real_receipt
    assert adapter.LONGITUDINAL_GBM_REACTOME_TRANSITION_REQUEST_MAX_BYTES == 2 * _MEBIBYTE
    assert adapter.LONGITUDINAL_GBM_REACTOME_TRANSITION_RESULT_MAX_BYTES == 4 * _MEBIBYTE
    assert adapter.LONGITUDINAL_GBM_REACTOME_TRANSITION_REPLAY_MAX_BYTES == 8 * _MEBIBYTE
    assert (
        adapter.LONGITUDINAL_GBM_REACTOME_TRANSITION_MAX_CONCURRENT_ANALYSES
        == _EXPECTED_CONCURRENCY
    )
    assert (
        adapter.LONGITUDINAL_GBM_REACTOME_TRANSITION_TIMEOUT_SECONDS
        == _EXPECTED_TIMEOUT_SECONDS
    )
    assert request.series_id == DEMO_ID
    assert len(result.transitions) == _EXPECTED_TRANSITIONS
    assert verification.verified is True


def test_fail_closed_mount_preflights_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    before = tuple(app.routes)
    monkeypatch.setattr(
        adapter,
        "algorithm_profile",
        partial(_raise_failure, ReactomeConditionalModelIntegrityError(_SENSITIVE)),
    )
    with pytest.raises(ReactomeConditionalModelIntegrityError, match=_SENSITIVE):
        adapter.mount_longitudinal_gbm_reactome_transition(app)
    assert tuple(app.routes) == before


def test_central_application_fails_closed_on_profile_integrity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        adapter,
        "algorithm_profile",
        partial(_raise_failure, ReactomeConditionalModelIntegrityError(_SENSITIVE)),
    )
    with pytest.raises(ReactomeConditionalModelIntegrityError, match=_SENSITIVE):
        create_app(tmp_path / "events.sqlite3")


def test_http_lifecycle_openapi_and_forgery(
    monkeypatch: pytest.MonkeyPatch,
    real_receipt: Receipt,
) -> None:
    request, result, verification = real_receipt
    forged_verification = verification.model_copy(
        update={"verified": False, "result_digest_match": False}
    )
    monkeypatch.setattr(
        adapter,
        "analyze_longitudinal_gbm_reactome_transition",
        lambda *_args, **_kwargs: result,
    )
    monkeypatch.setattr(
        adapter,
        "verify_longitudinal_gbm_reactome_transition_replay",
        lambda envelope, **_kwargs: (
            verification
            if envelope.result.result_digest == result.result_digest
            else forged_verification
        ),
    )
    with TestClient(_app()) as client:
        profile_response = client.get(f"{_PREFIX}/profile")
        demo_response = client.get(f"{_PREFIX}/demo")
        analysis_response = client.post(f"{_PREFIX}/analyze", json=request.model_dump(mode="json"))
        result_document = analysis_response.json()
        verification_response = client.post(
            f"{_PREFIX}/verify",
            json={"request": request.model_dump(mode="json"), "result": result_document},
        )
        forged = {**result_document, "result_digest": "sha256:" + "f" * 64}
        forged_response = client.post(
            f"{_PREFIX}/verify",
            json={"request": request.model_dump(mode="json"), "result": forged},
        )
        schema = client.get("/openapi.json").json()

    assert profile_response.status_code == _HTTP_OK
    assert profile_response.json()["profile_id"] == ALGORITHM_PROFILE_ID
    assert demo_response.status_code == _HTTP_OK
    assert analysis_response.status_code == _HTTP_OK, analysis_response.text
    assert verification_response.json()["verified"] is True
    assert forged_response.json()["verified"] is False
    assert analysis_response.headers["x-glio-result-digest"] == result.result_digest
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
    replay = schema["components"]["schemas"][
        "ReactomeConditionalReplayVerificationRequest"
    ]
    assert {item["$ref"] for item in replay["properties"]["result"]["anyOf"]} == {
        "#/components/schemas/LongitudinalGbmReactomeTransitionResult",
        "#/components/schemas/UnverifiedLongitudinalGbmReactomeTransitionResult",
    }


def test_transport_metadata_media_duplicate_and_oversize() -> None:
    no_length = _stream_request(b"{}")
    adapter._declared_content_length(no_length, 2)
    malformed_length = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-length", b"invalid")],
        }
    )
    negative_length = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-length", b"-1")],
        }
    )
    oversized_length = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-length", b"3")],
        }
    )
    for request in (malformed_length, negative_length):
        with pytest.raises(HTTPException) as captured:
            adapter._declared_content_length(request, 2)
        assert captured.value.status_code == _HTTP_BAD_REQUEST
    with pytest.raises(HTTPException) as captured:
        adapter._declared_content_length(oversized_length, 2)
    assert captured.value.status_code == _HTTP_PAYLOAD_TOO_LARGE

    with TestClient(_app()) as client:
        wrong_media = client.post(
            f"{_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        duplicate_json = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"series_id":"patient-a","series_id":"patient-b"}',
            headers={"content-type": "application/json"},
        )
        oversized = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"padding":"'
            + b"x" * adapter.LONGITUDINAL_GBM_REACTOME_TRANSITION_REQUEST_MAX_BYTES
            + b'"}',
            headers={"content-type": "application/json"},
        )
    assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA
    assert duplicate_json.status_code == _HTTP_UNPROCESSABLE
    assert "patient-" not in duplicate_json.text
    assert oversized.status_code == _HTTP_PAYLOAD_TOO_LARGE


def test_stream_bound_and_disconnect() -> None:
    with pytest.raises(HTTPException) as oversized:
        asyncio.run(adapter._bounded_body(_stream_request(b"ab", b"cd"), 3))
    assert oversized.value.status_code == _HTTP_PAYLOAD_TOO_LARGE
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
def test_typed_body_maps_cooperative_failures(
    failure: Exception,
    expected_status: int,
) -> None:
    body = synthetic_demo_request().model_dump_json().encode()
    cancellation = cast("CancellationContext", _CheckpointFailure(failure))
    with pytest.raises(HTTPException) as captured:
        asyncio.run(
            adapter._typed_body(
                _stream_request(body),
                adapter._REQUEST_ADAPTER,
                adapter.LONGITUDINAL_GBM_REACTOME_TRANSITION_REQUEST_MAX_BYTES,
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
                adapter.LONGITUDINAL_GBM_REACTOME_TRANSITION_REQUEST_MAX_BYTES,
                CancellationContext(),
            )
        )
    assert captured.value.status_code == _HTTP_TIMEOUT


def test_capacity_rejected_before_body_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", _UnavailableSlots())
    with TestClient(_app()) as client:
        analysis = client.post(f"{_PREFIX}/analyze", content=b"not-json")
        verification = client.post(f"{_PREFIX}/verify", content=b"not-json")
    assert analysis.status_code == _HTTP_TOO_MANY_REQUESTS
    assert verification.status_code == _HTTP_TOO_MANY_REQUESTS
    assert analysis.headers["retry-after"] == "1"
    assert analysis.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (ValueError(_SENSITIVE), _HTTP_UNPROCESSABLE),
        (ReactomeTransitionSourceIntegrityError(_SENSITIVE), _HTTP_UNAVAILABLE),
        (ReactomeConditionalModelIntegrityError(_SENSITIVE), _HTTP_UNAVAILABLE),
        (ReactomeConditionalInferenceError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
        (InferenceCancelledError(_SENSITIVE), _HTTP_CLIENT_CLOSED),
        (InferenceDeadlineExceededError(_SENSITIVE), _HTTP_TIMEOUT),
        (RuntimeError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
    ],
)
def test_execution_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status: int,
) -> None:
    slot = _TrackingSlot()
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)
    monkeypatch.setattr(
        adapter,
        "analyze_longitudinal_gbm_reactome_transition",
        partial(_raise_failure, failure),
    )
    with pytest.raises(HTTPException) as captured:
        adapter._execute(synthetic_demo_request())
    assert captured.value.status_code == status
    assert _SENSITIVE not in str(captured.value.detail)
    assert slot.released is True


def test_direct_capacity_success_and_result_receipt_bounds(
    monkeypatch: pytest.MonkeyPatch,
    real_receipt: Receipt,
) -> None:
    request, result, _verification = real_receipt
    with monkeypatch.context() as context:
        context.setattr(adapter, "_ANALYSIS_SLOTS", _UnavailableSlots())
        with pytest.raises(HTTPException) as capacity:
            adapter._execute(request)
    assert capacity.value.status_code == _HTTP_TOO_MANY_REQUESTS

    monkeypatch.setattr(
        adapter,
        "analyze_longitudinal_gbm_reactome_transition",
        lambda *_args, **_kwargs: result,
    )
    assert adapter._execute(request, admitted=True) is result
    with monkeypatch.context() as context:
        context.setattr(adapter, "LONGITUDINAL_GBM_REACTOME_TRANSITION_RESULT_MAX_BYTES", 1)
        with pytest.raises(HTTPException) as result_bound:
            adapter._execute(request)
    assert result_bound.value.status_code == _HTTP_INTERNAL_ERROR
    with monkeypatch.context() as context:
        context.setattr(
            adapter,
            "LONGITUDINAL_GBM_REACTOME_TRANSITION_RESULT_MAX_BYTES",
            _MEBIBYTE,
        )
        context.setattr(adapter, "LONGITUDINAL_GBM_REACTOME_TRANSITION_REPLAY_MAX_BYTES", 1)
        with pytest.raises(HTTPException) as receipt_bound:
            adapter._execute(request)
    assert receipt_bound.value.status_code == _HTTP_INTERNAL_ERROR


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (ValueError(_SENSITIVE), _HTTP_UNPROCESSABLE),
        (ReactomeTransitionSourceIntegrityError(_SENSITIVE), _HTTP_UNAVAILABLE),
        (ReactomeConditionalModelIntegrityError(_SENSITIVE), _HTTP_UNAVAILABLE),
        (ReactomeConditionalInferenceError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
        (InferenceCancelledError(_SENSITIVE), _HTTP_CLIENT_CLOSED),
        (InferenceDeadlineExceededError(_SENSITIVE), _HTTP_TIMEOUT),
        (RuntimeError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
    ],
)
def test_verification_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    real_receipt: Receipt,
    failure: Exception,
    status: int,
) -> None:
    request, result, _verification = real_receipt
    envelope = ReactomeConditionalReplayVerificationRequest(request=request, result=result)
    slot = _TrackingSlot()
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)
    monkeypatch.setattr(
        adapter,
        "verify_longitudinal_gbm_reactome_transition_replay",
        partial(_raise_failure, failure),
    )
    with pytest.raises(HTTPException) as captured:
        adapter._execute_verification(envelope)
    assert captured.value.status_code == status
    assert _SENSITIVE not in str(captured.value.detail)
    assert slot.released is True


def test_verification_capacity_success_and_bound(
    monkeypatch: pytest.MonkeyPatch,
    real_receipt: Receipt,
) -> None:
    request, result, verification = real_receipt
    envelope = ReactomeConditionalReplayVerificationRequest(request=request, result=result)
    with monkeypatch.context() as context:
        context.setattr(adapter, "_ANALYSIS_SLOTS", _UnavailableSlots())
        with pytest.raises(HTTPException) as capacity:
            adapter._execute_verification(envelope)
    assert capacity.value.status_code == _HTTP_TOO_MANY_REQUESTS
    monkeypatch.setattr(
        adapter,
        "verify_longitudinal_gbm_reactome_transition_replay",
        lambda *_args, **_kwargs: verification,
    )
    assert adapter._execute_verification(envelope, admitted=True) is verification
    with monkeypatch.context() as context:
        context.setattr(adapter, "LONGITUDINAL_GBM_REACTOME_TRANSITION_RESULT_MAX_BYTES", 1)
        with pytest.raises(HTTPException) as result_bound:
            adapter._execute_verification(envelope)
    assert result_bound.value.status_code == _HTTP_INTERNAL_ERROR


@pytest.mark.parametrize(
    ("path", "target", "failure", "status"),
    [
        (
            "profile",
            "algorithm_profile",
            ReactomeConditionalModelIntegrityError(_SENSITIVE),
            _HTTP_UNAVAILABLE,
        ),
        ("profile", "algorithm_profile", RuntimeError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
        (
            "demo",
            "synthetic_demo_request",
            ReactomeTransitionSourceIntegrityError(_SENSITIVE),
            _HTTP_UNAVAILABLE,
        ),
        ("demo", "synthetic_demo_request", RuntimeError(_SENSITIVE), _HTTP_INTERNAL_ERROR),
    ],
)
def test_read_endpoints_sanitize_failures(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    target: str,
    failure: Exception,
    status: int,
) -> None:
    application = _app()
    monkeypatch.setattr(adapter, target, partial(_raise_failure, failure))
    with TestClient(application) as client:
        response = client.get(f"{_PREFIX}/{path}")
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert _SENSITIVE not in response.text


def test_standalone_cli_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    real_receipt: Receipt,
) -> None:
    request, result, verification = real_receipt
    monkeypatch.setattr(
        adapter,
        "analyze_longitudinal_gbm_reactome_transition",
        lambda *_args, **_kwargs: result,
    )
    monkeypatch.setattr(
        adapter,
        "verify_longitudinal_gbm_reactome_transition_replay",
        lambda *_args, **_kwargs: verification,
    )
    runner = CliRunner()
    profile = runner.invoke(adapter.cli, ["profile"])
    demo = runner.invoke(adapter.cli, ["demo"])
    assert profile.exit_code == 0, profile.output
    assert demo.exit_code == 0, demo.output
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    analysis = runner.invoke(adapter.cli, ["analyze", str(request_path)])
    assert analysis.exit_code == 0, analysis.output
    result_document = json.loads(analysis.output)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps({"request": request.model_dump(mode="json"), "result": result_document}),
        encoding="utf-8",
    )
    replay = runner.invoke(adapter.cli, ["verify", str(receipt_path)])
    assert replay.exit_code == 0, replay.output
    assert json.loads(replay.output)["verified"] is True

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(
        '{"series_id":"patient-a","series_id":"patient-b"}',
        encoding="utf-8",
    )
    invalid = runner.invoke(adapter.cli, ["analyze", str(invalid_path)])
    assert invalid.exit_code != 0
    assert "patient-" not in invalid.output


def test_cli_failures_bounds_false_replay_and_text_stream(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    real_receipt: Receipt,
) -> None:
    request, result, verification = real_receipt
    envelope = ReactomeConditionalReplayVerificationRequest(request=request, result=result)
    request_path = tmp_path / "request.json"
    receipt_path = tmp_path / "receipt.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    receipt_path.write_text(envelope.model_dump_json(), encoding="utf-8")

    for target, command in (
        ("algorithm_profile", adapter.cli_profile),
        ("synthetic_demo_request", adapter.cli_demo),
    ):
        with monkeypatch.context() as context:
            context.setattr(
                adapter,
                target,
                partial(_raise_failure, RuntimeError(_SENSITIVE)),
            )
            with pytest.raises(adapter.LongitudinalGbmReactomeTransitionCliError):
                command()

    for target, path_command, path in (
        (
            "analyze_longitudinal_gbm_reactome_transition",
            adapter.cli_analyze,
            request_path,
        ),
        (
            "verify_longitudinal_gbm_reactome_transition_replay",
            adapter.cli_verify,
            receipt_path,
        ),
    ):
        with monkeypatch.context() as context:
            context.setattr(
                adapter,
                target,
                partial(_raise_failure, RuntimeError(_SENSITIVE)),
            )
            with pytest.raises(adapter.LongitudinalGbmReactomeTransitionCliError):
                path_command(path)

    with monkeypatch.context() as context:
        context.setattr(
            adapter,
            "analyze_longitudinal_gbm_reactome_transition",
            lambda *_args: result,
        )
        context.setattr(adapter, "LONGITUDINAL_GBM_REACTOME_TRANSITION_RESULT_MAX_BYTES", 1)
        with pytest.raises(adapter.LongitudinalGbmReactomeTransitionCliError):
            adapter.cli_analyze(request_path)
    with monkeypatch.context() as context:
        context.setattr(
            adapter,
            "analyze_longitudinal_gbm_reactome_transition",
            lambda *_args: result,
        )
        context.setattr(adapter, "LONGITUDINAL_GBM_REACTOME_TRANSITION_REPLAY_MAX_BYTES", 1)
        with pytest.raises(adapter.LongitudinalGbmReactomeTransitionCliError):
            adapter.cli_analyze(request_path)
    with monkeypatch.context() as context:
        context.setattr(
            adapter,
            "verify_longitudinal_gbm_reactome_transition_replay",
            lambda *_args: verification,
        )
        context.setattr(adapter, "LONGITUDINAL_GBM_REACTOME_TRANSITION_RESULT_MAX_BYTES", 1)
        with pytest.raises(adapter.LongitudinalGbmReactomeTransitionCliError):
            adapter.cli_verify(receipt_path)

    false_verification = verification.model_copy(update={"verified": False})
    with monkeypatch.context() as context:
        context.setattr(
            adapter,
            "verify_longitudinal_gbm_reactome_transition_replay",
            lambda *_args: false_verification,
        )
        with pytest.raises(adapter.typer.Exit) as exited:  # type: ignore[attr-defined]
            adapter.cli_verify(receipt_path)
    assert exited.value.exit_code == 1

    stream = StringIO()
    monkeypatch.setattr(
        "glio_proteogen.adapters.longitudinal_gbm_reactome_transition.sys.stdout",
        stream,
    )
    adapter._emit({"series": "GBM-δ"})
    assert stream.getvalue() == '{"series":"GBM-δ"}\n\n'


def test_disconnect_watcher_timeout_loop_and_close() -> None:
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

    async def loop_once() -> None:
        class ConnectedRequest:
            async def is_disconnected(self) -> bool:
                return False

        finished = asyncio.Event()
        watcher = asyncio.create_task(
            adapter._watch_disconnect(
                cast("Request", ConnectedRequest()),
                CancellationContext(),
                finished,
            )
        )
        await asyncio.sleep(adapter._DISCONNECT_POLL_SECONDS * 1.5)
        await adapter._close_watcher(finished, watcher)
        await adapter._close_watcher(finished, None)

    asyncio.run(loop_once())

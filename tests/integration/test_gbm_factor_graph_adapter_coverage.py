"""Exact defensive-branch coverage for the KNCC factor-graph adapter."""

from __future__ import annotations

import asyncio
import io
import json
import sys
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, cast

import pytest
import typer
from fastapi import HTTPException, Request, Response
from starlette.requests import ClientDisconnect

from glio_proteogen.adapters import gbm_factor_graph as adapter
from glio_proteogen.research.kncc_gbm_factor_graph.contracts import (
    KnccGbmFactorGraphReplayVerificationRequest,
    KnccGbmFactorGraphReplayVerificationResult,
    KnccGbmFactorGraphRequest,
    KnccGbmFactorGraphResult,
)
from glio_proteogen.research.kncc_gbm_factor_graph.demo import synthetic_demo_request
from glio_proteogen.research.kncc_gbm_factor_graph.errors import (
    KnccGbmFactorGraphProfileIntegrityError,
)
from glio_proteogen.research.kncc_gbm_factor_graph.service import (
    analyze_kncc_gbm_factor_graph,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

_HTTP_BAD_REQUEST = 400
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_CLIENT_CLOSED = 499
_HTTP_TIMEOUT = 504
_HTTP_TOO_MANY_REQUESTS = 429
_UNACQUIRED_MESSAGE = "unacquired capacity must not be released"


@dataclass
class _BodyRequest:
    chunks: tuple[bytes | Exception, ...]
    headers: dict[str, str]

    async def stream(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


@pytest.fixture(scope="module")
def receipt() -> tuple[
    KnccGbmFactorGraphRequest,
    KnccGbmFactorGraphResult,
    KnccGbmFactorGraphReplayVerificationResult,
]:
    request = synthetic_demo_request()
    result = analyze_kncc_gbm_factor_graph(request)
    verification = KnccGbmFactorGraphReplayVerificationResult(
        verified=True,
        request_digest_match=True,
        profile_digest_match=True,
        topology_digest_match=True,
        source_inventory_digest_match=True,
        result_digest_match=True,
        reactome_child_verified=True,
        kinase_child_verified=True,
        independent_parallel_blocks_match=True,
        no_cross_modal_fusion_match=True,
        no_numerical_cross_block_edges_match=True,
        provenance_match=True,
        document_semantic_match=True,
        semantic_match=True,
        recomputed_request_digest=result.request_digest,
        recomputed_result_digest=result.result_digest,
        message="exact replay",
    )
    return request, result, verification


def _raise(error: Exception) -> None:
    raise error


@pytest.mark.parametrize("raw", ["invalid", "-1"])
def test_declared_content_length_rejects_invalid_and_negative(raw: str) -> None:
    request = cast("Request", _BodyRequest((), {"content-length": raw}))
    with pytest.raises(HTTPException) as captured:
        adapter._declared_content_length(request, 10)
    assert captured.value.status_code == _HTTP_BAD_REQUEST
    assert captured.value.headers == {"Cache-Control": "no-store"}


def test_declared_content_length_absence_and_stream_guards() -> None:
    without_length = cast("Request", _BodyRequest((b"ab", b"cd"), {}))
    adapter._declared_content_length(without_length, 4)
    assert asyncio.run(adapter._bounded_body(without_length, 4)) == b"abcd"

    streaming_oversize = cast(
        "Request",
        _BodyRequest((b"abc", b"de"), {}),
    )
    with pytest.raises(HTTPException) as oversized:
        asyncio.run(adapter._bounded_body(streaming_oversize, 4))
    assert oversized.value.status_code == _HTTP_PAYLOAD_TOO_LARGE

    disconnected = cast(
        "Request",
        _BodyRequest((ClientDisconnect(),), {}),
    )
    with pytest.raises(HTTPException) as cancelled:
        asyncio.run(adapter._bounded_body(disconnected, 4))
    assert cancelled.value.status_code == _HTTP_CLIENT_CLOSED
    assert cancelled.value.detail == adapter._CANCELLED_MESSAGE


def test_typed_body_without_deadline_and_cooperative_failure_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    payload = request.model_dump_json().encode("utf-8")
    body_request = cast(
        "Request",
        _BodyRequest((payload,), {"content-type": "application/json"}),
    )
    decoded = asyncio.run(
        adapter._typed_body(
            body_request,
            adapter._REQUEST_ADAPTER,
            adapter.GBM_FACTOR_GRAPH_REQUEST_MAX_BYTES,
            CancellationContext(),
        )
    )
    assert decoded == request

    async def fail_with(error: Exception, *_args: object, **_kwargs: object) -> bytes:
        raise error

    for error, status in (
        (InferenceDeadlineExceededError("deadline"), _HTTP_TIMEOUT),
        (InferenceCancelledError("cancelled"), _HTTP_CLIENT_CLOSED),
    ):
        monkeypatch.setattr(adapter, "_bounded_body", partial(fail_with, error))
        with pytest.raises(HTTPException) as captured:
            asyncio.run(
                adapter._typed_body(
                    body_request,
                    adapter._REQUEST_ADAPTER,
                    adapter.GBM_FACTOR_GRAPH_REQUEST_MAX_BYTES,
                    CancellationContext(),
                )
            )
        assert captured.value.status_code == status


def test_direct_execution_capacity_guards(
    monkeypatch: pytest.MonkeyPatch,
    receipt: tuple[
        KnccGbmFactorGraphRequest,
        KnccGbmFactorGraphResult,
        KnccGbmFactorGraphReplayVerificationResult,
    ],
) -> None:
    request, result, _verification = receipt
    replay = KnccGbmFactorGraphReplayVerificationRequest(request=request, result=result)

    class NoCapacity:
        def acquire(self, *, blocking: bool) -> bool:
            assert blocking is False
            return False

        def release(self) -> None:
            raise AssertionError(_UNACQUIRED_MESSAGE)

    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", NoCapacity())
    with pytest.raises(HTTPException) as analysis:
        adapter._execute(request)
    with pytest.raises(HTTPException) as verification:
        adapter._execute_verification(replay)
    for captured in (analysis, verification):
        assert captured.value.status_code == _HTTP_TOO_MANY_REQUESTS
        assert captured.value.headers == {"Cache-Control": "no-store", "Retry-After": "1"}


@pytest.mark.parametrize(
    ("endpoint", "failure", "status", "detail"),
    [
        (
            adapter.profile,
            KnccGbmFactorGraphProfileIntegrityError("private"),
            503,
            adapter._UNAVAILABLE_MESSAGE,
        ),
        (adapter.profile, RuntimeError("private"), 500, adapter._ANALYSIS_ERROR_MESSAGE),
        (
            adapter.demo,
            KnccGbmFactorGraphProfileIntegrityError("private"),
            503,
            adapter._UNAVAILABLE_MESSAGE,
        ),
        (adapter.demo, RuntimeError("private"), 500, adapter._ANALYSIS_ERROR_MESSAGE),
    ],
)
def test_profile_and_demo_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: Callable[[Response], object],
    failure: Exception,
    status: int,
    detail: str,
) -> None:
    target = "algorithm_profile" if endpoint is adapter.profile else "synthetic_demo_request"
    monkeypatch.setattr(adapter, target, lambda: _raise(failure))
    with pytest.raises(HTTPException) as captured:
        endpoint(Response())
    assert captured.value.status_code == status
    assert captured.value.detail == detail
    assert "private" not in str(captured.value.detail)


def test_emit_without_binary_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    adapter._emit({"ok": True})
    assert json.loads(stream.getvalue()) == {"ok": True}


def test_cli_profile_demo_and_analysis_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    receipt: tuple[
        KnccGbmFactorGraphRequest,
        KnccGbmFactorGraphResult,
        KnccGbmFactorGraphReplayVerificationResult,
    ],
) -> None:
    request, result, _verification = receipt
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(adapter, "_emit", lambda _value: None)

    with monkeypatch.context() as context:
        context.setattr(adapter, "algorithm_profile", lambda: _raise(RuntimeError("private")))
        with pytest.raises(adapter.GbmFactorGraphCliError, match=adapter._UNAVAILABLE_MESSAGE):
            adapter.cli_profile()
    with monkeypatch.context() as context:
        context.setattr(
            adapter,
            "synthetic_demo_request",
            lambda: _raise(RuntimeError("private")),
        )
        with pytest.raises(adapter.GbmFactorGraphCliError, match=adapter._ANALYSIS_ERROR_MESSAGE):
            adapter.cli_demo()
    with monkeypatch.context() as context:
        context.setattr(
            adapter,
            "analyze_kncc_gbm_factor_graph",
            lambda *_a, **_k: _raise(RuntimeError("private")),
        )
        with pytest.raises(adapter.GbmFactorGraphCliError, match=adapter._ANALYSIS_ERROR_MESSAGE):
            adapter.cli_analyze(request_path)
    with monkeypatch.context() as context:
        context.setattr(adapter, "analyze_kncc_gbm_factor_graph", lambda *_a, **_k: result)
        context.setattr(adapter, "GBM_FACTOR_GRAPH_RESULT_MAX_BYTES", 1)
        with pytest.raises(adapter.GbmFactorGraphCliError, match=adapter._ANALYSIS_ERROR_MESSAGE):
            adapter.cli_analyze(request_path)
    with monkeypatch.context() as context:
        context.setattr(adapter, "analyze_kncc_gbm_factor_graph", lambda *_a, **_k: result)
        context.setattr(adapter, "GBM_FACTOR_GRAPH_REPLAY_MAX_BYTES", 1)
        with pytest.raises(adapter.GbmFactorGraphCliError, match=adapter._ANALYSIS_ERROR_MESSAGE):
            adapter.cli_analyze(request_path)


def test_cli_verification_failure_size_and_mismatch_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    receipt: tuple[
        KnccGbmFactorGraphRequest,
        KnccGbmFactorGraphResult,
        KnccGbmFactorGraphReplayVerificationResult,
    ],
) -> None:
    request, result, verification = receipt
    replay_path = tmp_path / "replay.json"
    replay_path.write_text(
        json.dumps(
            {
                "request": request.model_dump(mode="json"),
                "result": result.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(adapter, "_emit", lambda _value: None)

    with monkeypatch.context() as context:
        context.setattr(
            adapter,
            "verify_kncc_gbm_factor_graph_replay",
            lambda *_a, **_k: _raise(RuntimeError("private")),
        )
        with pytest.raises(adapter.GbmFactorGraphCliError, match=adapter._REPLAY_ERROR_MESSAGE):
            adapter.cli_verify(replay_path)
    with monkeypatch.context() as context:
        context.setattr(
            adapter,
            "verify_kncc_gbm_factor_graph_replay",
            lambda *_a, **_k: verification,
        )
        context.setattr(adapter, "GBM_FACTOR_GRAPH_RESULT_MAX_BYTES", 1)
        with pytest.raises(adapter.GbmFactorGraphCliError, match=adapter._REPLAY_ERROR_MESSAGE):
            adapter.cli_verify(replay_path)
    with monkeypatch.context() as context:
        mismatch = verification.model_copy(update={"verified": False, "result_digest_match": False})
        context.setattr(
            adapter,
            "verify_kncc_gbm_factor_graph_replay",
            lambda *_a, **_k: mismatch,
        )
        with pytest.raises(typer.Exit) as captured:
            adapter.cli_verify(replay_path)
        assert captured.value.exit_code == 1

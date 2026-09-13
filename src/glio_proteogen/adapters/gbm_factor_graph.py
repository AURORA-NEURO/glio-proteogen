"""Bounded HTTP and CLI boundary for the KNCC GBM factor graph."""

from __future__ import annotations

import asyncio
import sys
from functools import partial
from pathlib import Path  # noqa: TC003 - Typer resolves path annotations at runtime.
from threading import BoundedSemaphore
from typing import TYPE_CHECKING, Annotated, Any, Final

import anyio
import typer
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import TypeAdapter, ValidationError
from starlette.requests import ClientDisconnect

from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.research.kncc_gbm_factor_graph.contracts import (
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    KnccGbmFactorGraphProfile,
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
from glio_proteogen.research.kncc_gbm_factor_graph.profile import algorithm_profile
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
    from fastapi import FastAPI

GBM_FACTOR_GRAPH_ROUTE_PREFIX: Final = "/v1/research/gbm-factor-graph"
GBM_FACTOR_GRAPH_REQUEST_MAX_BYTES: Final = MAX_REQUEST_BYTES
GBM_FACTOR_GRAPH_RESULT_MAX_BYTES: Final = MAX_RESULT_BYTES
GBM_FACTOR_GRAPH_REPLAY_MAX_BYTES: Final = MAX_REPLAY_BYTES
GBM_FACTOR_GRAPH_MAX_CONCURRENT_ANALYSES: Final = 1
GBM_FACTOR_GRAPH_TIMEOUT_SECONDS: Final = 120.0
GBM_FACTOR_GRAPH_RETRY_AFTER_SECONDS: Final = 1
_DISCONNECT_POLL_SECONDS: Final = 0.05
_CANCELLED_MESSAGE: Final = "GBM factor-graph computation was cancelled"
_TIMEOUT_MESSAGE: Final = "GBM factor-graph computation exceeded its deadline"
_ANALYSIS_ERROR_MESSAGE: Final = "GBM factor-graph analysis failed safely"
_REPLAY_ERROR_MESSAGE: Final = "GBM factor-graph replay failed safely"
_UNAVAILABLE_MESSAGE: Final = "GBM factor-graph model is unavailable"
_CLI_INPUT_ERROR_MESSAGE: Final = "input does not satisfy the GBM factor-graph contract"

_REQUEST_ADAPTER: Final = TypeAdapter(KnccGbmFactorGraphRequest)
_REPLAY_ADAPTER: Final = TypeAdapter(KnccGbmFactorGraphReplayVerificationRequest)
_ANALYSIS_SLOTS = BoundedSemaphore(GBM_FACTOR_GRAPH_MAX_CONCURRENT_ANALYSES)

router = APIRouter(
    prefix=GBM_FACTOR_GRAPH_ROUTE_PREFIX,
    tags=["research-gbm-factor-graph"],
)
cli = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Run and replay research-only KNCC GBM factor-graph inference.",
)


class GbmFactorGraphCliError(typer.BadParameter):
    """Sanitized KNCC GBM factor-graph command-line validation error."""


def _error_headers(**values: str) -> dict[str, str]:
    return {"Cache-Control": "no-store", **values}


def _http_error(status_code: int, detail: str, **headers: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers=_error_headers(**headers),
    )


def _declared_content_length(request: Request, max_bytes: int) -> None:
    raw = request.headers.get("content-length")
    if raw is None:
        return
    try:
        declared = int(raw)
    except ValueError:
        raise _http_error(400, "invalid content-length") from None
    if declared < 0:
        raise _http_error(400, "invalid content-length")
    if declared > max_bytes:
        raise _http_error(413, "request body exceeds the byte limit")


async def _bounded_body(request: Request, max_bytes: int) -> bytes:
    _declared_content_length(request, max_bytes)
    chunks: list[bytes] = []
    received = 0
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > max_bytes:
                raise _http_error(413, "request body exceeds the byte limit")
            chunks.append(chunk)
    except ClientDisconnect:
        raise _http_error(499, _CANCELLED_MESSAGE) from None
    return b"".join(chunks)


def _decode_typed[T](body: bytes, adapter: TypeAdapter[T], max_bytes: int) -> T:
    strict_json_loads(body, max_bytes=max_bytes)
    return adapter.validate_json(body, strict=True)


async def _typed_body[T](
    request: Request,
    adapter: TypeAdapter[T],
    max_bytes: int,
    cancellation: CancellationContext,
) -> T:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise _http_error(415, "content-type must be application/json")
    try:
        remaining = cancellation.remaining_seconds()
        if remaining is None:
            body = await _bounded_body(request, max_bytes)
        else:
            async with asyncio.timeout(remaining):
                body = await _bounded_body(request, max_bytes)
        cancellation.checkpoint()
        typed = await anyio.to_thread.run_sync(partial(_decode_typed, body, adapter, max_bytes))
        cancellation.checkpoint()
    except TimeoutError:
        raise _http_error(504, _TIMEOUT_MESSAGE) from None
    except InferenceDeadlineExceededError:
        raise _http_error(504, _TIMEOUT_MESSAGE) from None
    except InferenceCancelledError:
        raise _http_error(499, _CANCELLED_MESSAGE) from None
    except (StrictJsonError, ValidationError):
        raise _http_error(422, "request does not satisfy the GBM factor-graph contract") from None
    else:
        return typed


def _request_body_schema(schema: dict[str, object]) -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": schema}},
        }
    }


_ERROR_SCHEMA: Final = {
    "type": "object",
    "additionalProperties": False,
    "required": ["detail"],
    "properties": {"detail": {"type": "string"}},
}


def _error_response(
    description: str,
    *,
    headers: dict[str, object] | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "description": description,
        "content": {"application/json": {"schema": _ERROR_SCHEMA}},
    }
    if headers is not None:
        response["headers"] = headers
    return response


_ERROR_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    400: _error_response("Invalid transport metadata"),
    413: _error_response("Request body exceeds the declared byte limit"),
    415: _error_response("Unsupported request media type"),
    422: _error_response("Request is not evaluable"),
    429: _error_response(
        "Research execution capacity is exhausted",
        headers={
            "Retry-After": {
                "description": "Seconds before retrying admission",
                "schema": {"type": "integer", "minimum": 1},
            }
        },
    ),
    499: _error_response("Caller disconnected or cancelled execution"),
    500: _error_response("Sanitized internal research failure"),
    503: _error_response("Locked research model is unavailable"),
    504: _error_response("Research execution deadline exceeded"),
}


def install_gbm_factor_graph_openapi(app: FastAPI) -> None:
    """Publish the exact strict replay envelope in shared OpenAPI."""

    original_openapi = app.openapi
    replay_schema = _REPLAY_ADAPTER.json_schema(ref_template="#/components/schemas/{model}")
    definitions = replay_schema.pop("$defs")

    def openapi_with_replay_contract() -> dict[str, Any]:
        schema = original_openapi()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, definition in definitions.items():
            components.setdefault(name, definition)
        component_name = "KnccGbmFactorGraphReplayVerificationRequest"
        components[component_name] = replay_schema
        operation = schema["paths"][f"{GBM_FACTOR_GRAPH_ROUTE_PREFIX}/verify"]["post"]
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {"schema": {"$ref": f"#/components/schemas/{component_name}"}}
            },
        }
        app.openapi_schema = schema
        return schema

    app.__dict__["openapi"] = openapi_with_replay_contract


def mount_gbm_factor_graph(app: FastAPI) -> None:
    """Preflight locked artifacts before exposing any factor-graph route."""

    algorithm_profile()
    app.include_router(router)


def _acquire_http_slot() -> None:
    if not _ANALYSIS_SLOTS.acquire(blocking=False):
        raise _http_error(
            429,
            "GBM factor-graph capacity is exhausted",
            **{"Retry-After": str(GBM_FACTOR_GRAPH_RETRY_AFTER_SECONDS)},
        )


async def _watch_disconnect(
    request: Request,
    cancellation: CancellationContext,
    finished: asyncio.Event,
) -> None:
    while not finished.is_set():
        if await request.is_disconnected():
            cancellation.cancel()
            return
        try:
            await asyncio.wait_for(finished.wait(), timeout=_DISCONNECT_POLL_SECONDS)
        except TimeoutError:
            continue


async def _close_watcher(finished: asyncio.Event, watcher: asyncio.Task[None] | None) -> None:
    finished.set()
    if watcher is not None:
        await watcher


def _capacity_error() -> HTTPException:
    return _http_error(
        429,
        "GBM factor-graph capacity is exhausted",
        **{"Retry-After": str(GBM_FACTOR_GRAPH_RETRY_AFTER_SECONDS)},
    )


def _execute(  # noqa: C901 - explicit boundary mapping is intentionally exhaustive.
    request: KnccGbmFactorGraphRequest,
    cancellation: CancellationContext | None = None,
    *,
    admitted: bool = False,
) -> KnccGbmFactorGraphResult:
    acquired = admitted or _ANALYSIS_SLOTS.acquire(blocking=False)
    if not acquired:
        raise _capacity_error()
    try:
        result = analyze_kncc_gbm_factor_graph(request, cancellation=cancellation)
    except InferenceDeadlineExceededError:
        raise _http_error(504, _TIMEOUT_MESSAGE) from None
    except InferenceCancelledError:
        raise _http_error(499, _CANCELLED_MESSAGE) from None
    except KnccGbmFactorGraphProfileIntegrityError:
        raise _http_error(503, _UNAVAILABLE_MESSAGE) from None
    except KnccGbmFactorGraphInferenceError:
        raise _http_error(500, _ANALYSIS_ERROR_MESSAGE) from None
    except (TypeError, ValueError, ValidationError):
        raise _http_error(
            422,
            "request could not be evaluated by the GBM factor-graph model",
        ) from None
    except Exception:  # noqa: BLE001 - sanitize unexpected failures at the boundary.
        raise _http_error(500, _ANALYSIS_ERROR_MESSAGE) from None
    finally:
        if not admitted:
            _ANALYSIS_SLOTS.release()
    if len(canonical_json_bytes(result)) > GBM_FACTOR_GRAPH_RESULT_MAX_BYTES:
        raise _http_error(500, "GBM factor-graph result exceeded its transport bound")
    receipt_size = len(canonical_json_bytes({"request": request, "result": result}))
    if receipt_size > GBM_FACTOR_GRAPH_REPLAY_MAX_BYTES:
        raise _http_error(500, "GBM factor-graph receipt exceeded its replay bound")
    return result


def _execute_verification(
    request: KnccGbmFactorGraphReplayVerificationRequest,
    cancellation: CancellationContext | None = None,
    *,
    admitted: bool = False,
) -> KnccGbmFactorGraphReplayVerificationResult:
    acquired = admitted or _ANALYSIS_SLOTS.acquire(blocking=False)
    if not acquired:
        raise _capacity_error()
    try:
        result = verify_kncc_gbm_factor_graph_replay(request, cancellation=cancellation)
    except InferenceDeadlineExceededError:
        raise _http_error(504, _TIMEOUT_MESSAGE) from None
    except InferenceCancelledError:
        raise _http_error(499, _CANCELLED_MESSAGE) from None
    except KnccGbmFactorGraphProfileIntegrityError:
        raise _http_error(503, _UNAVAILABLE_MESSAGE) from None
    except KnccGbmFactorGraphReplayError:
        raise _http_error(500, _REPLAY_ERROR_MESSAGE) from None
    except (TypeError, ValueError, ValidationError):
        raise _http_error(422, "replay envelope is invalid") from None
    except Exception:  # noqa: BLE001 - sanitize unexpected failures at the boundary.
        raise _http_error(500, _REPLAY_ERROR_MESSAGE) from None
    finally:
        if not admitted:
            _ANALYSIS_SLOTS.release()
    if len(canonical_json_bytes(result)) > GBM_FACTOR_GRAPH_RESULT_MAX_BYTES:
        raise _http_error(500, "GBM factor-graph verification exceeded its bound")
    return result


def _analysis_headers(response: Response, result: KnccGbmFactorGraphResult) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Profile-Digest"] = result.profile_digest
    response.headers["X-GLIO-Request-Digest"] = result.request_digest
    response.headers["X-GLIO-Result-Digest"] = result.result_digest


@router.get(
    "/profile",
    response_model=KnccGbmFactorGraphProfile,
    responses={500: _ERROR_RESPONSES[500], 503: _ERROR_RESPONSES[503]},
)
def profile(response: Response) -> KnccGbmFactorGraphProfile:
    """Return the source-locked KNCC GBM factor-graph profile."""

    try:
        result = algorithm_profile()
    except KnccGbmFactorGraphProfileIntegrityError:
        raise _http_error(503, _UNAVAILABLE_MESSAGE) from None
    except Exception:  # noqa: BLE001 - sanitize profile-integrity failures.
        raise _http_error(500, _ANALYSIS_ERROR_MESSAGE) from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Profile-Digest"] = result.profile_digest
    return result


@router.get(
    "/demo",
    response_model=KnccGbmFactorGraphRequest,
    responses={500: _ERROR_RESPONSES[500], 503: _ERROR_RESPONSES[503]},
)
def demo(response: Response) -> KnccGbmFactorGraphRequest:
    """Return the versioned wholly synthetic KNCC-shaped request."""

    try:
        result = synthetic_demo_request()
        profile_digest = algorithm_profile().profile_digest
    except KnccGbmFactorGraphProfileIntegrityError:
        raise _http_error(503, _UNAVAILABLE_MESSAGE) from None
    except Exception:  # noqa: BLE001 - sanitize demo-integrity failures.
        raise _http_error(500, _ANALYSIS_ERROR_MESSAGE) from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Profile-Digest"] = profile_digest
    response.headers["X-GLIO-Request-Digest"] = result.request_digest
    return result


@router.post(
    "/analyze",
    response_model=KnccGbmFactorGraphResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_request_body_schema({"$ref": "#/components/schemas/KnccGbmFactorGraphRequest"}),
)
async def analyze(request: Request, response: Response) -> KnccGbmFactorGraphResult:
    """Run bounded deterministic factor-graph inference off the event loop."""

    _acquire_http_slot()
    cancellation = CancellationContext.with_timeout(GBM_FACTOR_GRAPH_TIMEOUT_SECONDS)
    finished = asyncio.Event()
    watcher: asyncio.Task[None] | None = None
    try:
        typed = await _typed_body(
            request,
            _REQUEST_ADAPTER,
            GBM_FACTOR_GRAPH_REQUEST_MAX_BYTES,
            cancellation,
        )
        watcher = asyncio.create_task(_watch_disconnect(request, cancellation, finished))
        result = await anyio.to_thread.run_sync(
            partial(_execute, typed, cancellation, admitted=True)
        )
        _analysis_headers(response, result)
        return result
    finally:
        try:
            await _close_watcher(finished, watcher)
        finally:
            _ANALYSIS_SLOTS.release()


@router.post(
    "/verify",
    response_model=KnccGbmFactorGraphReplayVerificationResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_request_body_schema(
        {"$ref": "#/components/schemas/KnccGbmFactorGraphReplayVerificationRequest"}
    ),
)
async def verify(
    request: Request,
    response: Response,
) -> KnccGbmFactorGraphReplayVerificationResult:
    """Recompute one factor-graph request and verify its receipt."""

    _acquire_http_slot()
    cancellation = CancellationContext.with_timeout(GBM_FACTOR_GRAPH_TIMEOUT_SECONDS)
    finished = asyncio.Event()
    watcher: asyncio.Task[None] | None = None
    try:
        typed = await _typed_body(
            request,
            _REPLAY_ADAPTER,
            GBM_FACTOR_GRAPH_REPLAY_MAX_BYTES,
            cancellation,
        )
        watcher = asyncio.create_task(_watch_disconnect(request, cancellation, finished))
        result = await anyio.to_thread.run_sync(
            partial(_execute_verification, typed, cancellation, admitted=True)
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-GLIO-Profile-Digest"] = algorithm_profile().profile_digest
        response.headers["X-GLIO-Request-Digest"] = result.recomputed_request_digest
        response.headers["X-GLIO-Result-Digest"] = result.recomputed_result_digest
        return result
    finally:
        try:
            await _close_watcher(finished, watcher)
        finally:
            _ANALYSIS_SLOTS.release()


def _read_typed[T](path: Path, adapter: TypeAdapter[T], max_bytes: int) -> T:
    try:
        data = read_bounded(path, max_bytes)
        strict_json_loads(data, max_bytes=max_bytes)
        return adapter.validate_json(data, strict=True)
    except (
        OSError,
        RequestBodyTooLargeError,
        StrictJsonError,
        ValueError,
        ValidationError,
    ):
        raise GbmFactorGraphCliError(_CLI_INPUT_ERROR_MESSAGE) from None


def _emit(value: object) -> None:
    payload = canonical_json_bytes(value) + b"\n"
    binary_stream = getattr(sys.stdout, "buffer", None)
    if binary_stream is None:
        typer.echo(payload.decode("utf-8"))
        return
    binary_stream.write(payload)
    binary_stream.flush()


@cli.command("profile")
def cli_profile() -> None:
    """Print the source-locked KNCC GBM factor-graph profile."""

    try:
        result = algorithm_profile()
    except Exception:  # noqa: BLE001 - sanitize model-integrity failures.
        raise GbmFactorGraphCliError(_UNAVAILABLE_MESSAGE) from None
    _emit(result)


@cli.command("demo")
def cli_demo() -> None:
    """Print the versioned wholly synthetic KNCC-shaped request."""

    try:
        result = synthetic_demo_request()
    except Exception:  # noqa: BLE001 - sanitize demo-integrity failures.
        raise GbmFactorGraphCliError(_ANALYSIS_ERROR_MESSAGE) from None
    _emit(result)


@cli.command("analyze")
def cli_analyze(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Analyze one strict request without persisting it."""

    typed = _read_typed(request, _REQUEST_ADAPTER, GBM_FACTOR_GRAPH_REQUEST_MAX_BYTES)
    try:
        result = analyze_kncc_gbm_factor_graph(typed)
    except Exception:  # noqa: BLE001 - sanitize every numerical/model failure.
        raise GbmFactorGraphCliError(_ANALYSIS_ERROR_MESSAGE) from None
    if len(canonical_json_bytes(result)) > GBM_FACTOR_GRAPH_RESULT_MAX_BYTES:
        raise GbmFactorGraphCliError(_ANALYSIS_ERROR_MESSAGE)
    if (
        len(canonical_json_bytes({"request": typed, "result": result}))
        > GBM_FACTOR_GRAPH_REPLAY_MAX_BYTES
    ):
        raise GbmFactorGraphCliError(_ANALYSIS_ERROR_MESSAGE)
    _emit(result)


@cli.command("verify")
def cli_verify(
    envelope: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Replay and verify one request/result receipt."""

    typed = _read_typed(envelope, _REPLAY_ADAPTER, GBM_FACTOR_GRAPH_REPLAY_MAX_BYTES)
    try:
        result = verify_kncc_gbm_factor_graph_replay(typed)
    except Exception:  # noqa: BLE001 - sanitize every numerical/model failure.
        raise GbmFactorGraphCliError(_REPLAY_ERROR_MESSAGE) from None
    if len(canonical_json_bytes(result)) > GBM_FACTOR_GRAPH_RESULT_MAX_BYTES:
        raise GbmFactorGraphCliError(_REPLAY_ERROR_MESSAGE)
    _emit(result)
    if not result.verified:
        raise typer.Exit(code=1)


__all__ = [
    "GBM_FACTOR_GRAPH_MAX_CONCURRENT_ANALYSES",
    "GBM_FACTOR_GRAPH_REPLAY_MAX_BYTES",
    "GBM_FACTOR_GRAPH_REQUEST_MAX_BYTES",
    "GBM_FACTOR_GRAPH_RESULT_MAX_BYTES",
    "GBM_FACTOR_GRAPH_ROUTE_PREFIX",
    "GBM_FACTOR_GRAPH_TIMEOUT_SECONDS",
    "GbmFactorGraphCliError",
    "cli",
    "install_gbm_factor_graph_openapi",
    "mount_gbm_factor_graph",
    "router",
]

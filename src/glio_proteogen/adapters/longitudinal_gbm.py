"""Bounded HTTP and CLI boundary for longitudinal GBM protein concordance."""

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
from glio_proteogen.research.longitudinal_gbm.contracts import (
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    LongitudinalGbmProfile,
    LongitudinalGbmRequest,
    LongitudinalGbmResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
)
from glio_proteogen.research.longitudinal_gbm.demo import synthetic_demo_request
from glio_proteogen.research.longitudinal_gbm.errors import (
    LongitudinalGbmError,
    SourceProfileIntegrityError,
)
from glio_proteogen.research.longitudinal_gbm.m15_facade import (
    ROUTE_PREFIX as M15_LONGITUDINAL_RECURRENCE_ROUTE_PREFIX,
)
from glio_proteogen.research.longitudinal_gbm.m15_facade import (
    M15LongitudinalRecurrenceFacadeProfile,
    m15_facade_profile,
)
from glio_proteogen.research.longitudinal_gbm.profile import algorithm_profile
from glio_proteogen.research.longitudinal_gbm.service import (
    analyze_longitudinal_gbm,
    verify_longitudinal_gbm_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

LONGITUDINAL_GBM_ROUTE_PREFIX: Final = "/v1/research/longitudinal-gbm"
LONGITUDINAL_GBM_REQUEST_MAX_BYTES: Final = MAX_REQUEST_BYTES
LONGITUDINAL_GBM_RESULT_MAX_BYTES: Final = MAX_RESULT_BYTES
LONGITUDINAL_GBM_REPLAY_MAX_BYTES: Final = MAX_REPLAY_BYTES
LONGITUDINAL_GBM_MAX_CONCURRENT_ANALYSES: Final = 2
# A fully supported 16-point/12k-observation/256-replicate request is measured
# at roughly 67 seconds on the reference development host.  Keep the accepted
# envelope executable while cooperative cancellation still bounds the lane.
LONGITUDINAL_GBM_TIMEOUT_SECONDS: Final = 120.0
LONGITUDINAL_GBM_RETRY_AFTER_SECONDS: Final = 1
_DISCONNECT_POLL_SECONDS: Final = 0.05
_CANCELLED_MESSAGE: Final = "longitudinal GBM computation was cancelled"
_TIMEOUT_MESSAGE: Final = "longitudinal GBM computation exceeded its deadline"
_ANALYSIS_ERROR_MESSAGE: Final = "longitudinal GBM analysis failed safely"
_REPLAY_ERROR_MESSAGE: Final = "longitudinal GBM replay failed safely"
_CLI_INPUT_ERROR_MESSAGE: Final = "input does not satisfy the longitudinal GBM contract"

_REQUEST_ADAPTER: Final = TypeAdapter(LongitudinalGbmRequest)
_REPLAY_ADAPTER: Final = TypeAdapter(ReplayVerificationRequest)
_ANALYSIS_SLOTS = BoundedSemaphore(LONGITUDINAL_GBM_MAX_CONCURRENT_ANALYSES)

router = APIRouter(
    prefix=LONGITUDINAL_GBM_ROUTE_PREFIX,
    tags=["research-longitudinal-gbm"],
)
m15_router = APIRouter(
    prefix=M15_LONGITUDINAL_RECURRENCE_ROUTE_PREFIX,
    tags=["research-m15-longitudinal-recurrence-proteotype-evidence"],
)
cli = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Run and replay research-only longitudinal GBM protein concordance.",
)


class LongitudinalGbmCliError(typer.BadParameter):
    """Sanitized longitudinal GBM command-line validation error."""


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
        raise _http_error(422, "request does not satisfy the longitudinal GBM contract") from None
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
    422: _error_response("Request or longitudinal inference is not evaluable"),
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
    504: _error_response("Research execution deadline exceeded"),
}


def install_longitudinal_gbm_openapi(app: FastAPI) -> None:
    """Publish the exact strict replay envelope in shared OpenAPI."""

    original_openapi = app.openapi
    replay_schema = _REPLAY_ADAPTER.json_schema(ref_template="#/components/schemas/{model}")
    definitions = replay_schema.pop("$defs")

    def openapi_with_replay_contract() -> dict[str, Any]:
        schema = original_openapi()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, definition in definitions.items():
            components.setdefault(name, definition)
        components["LongitudinalGbmReplayVerificationRequest"] = replay_schema
        operation = schema["paths"][f"{LONGITUDINAL_GBM_ROUTE_PREFIX}/verify"]["post"]
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "$ref": "#/components/schemas/LongitudinalGbmReplayVerificationRequest"
                    }
                }
            },
        }
        for path, component in (
            (
                f"{M15_LONGITUDINAL_RECURRENCE_ROUTE_PREFIX}/analyze",
                "LongitudinalGbmRequest",
            ),
            (
                f"{M15_LONGITUDINAL_RECURRENCE_ROUTE_PREFIX}/verify",
                "LongitudinalGbmReplayVerificationRequest",
            ),
        ):
            path_document = schema["paths"].get(path)
            if path_document is None:
                continue
            path_document["post"]["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{component}"}}
                },
            }
        app.openapi_schema = schema
        return schema

    app.__dict__["openapi"] = openapi_with_replay_contract


def _acquire_http_slot() -> None:
    if not _ANALYSIS_SLOTS.acquire(blocking=False):
        raise _http_error(
            429,
            "longitudinal GBM capacity is exhausted",
            **{"Retry-After": str(LONGITUDINAL_GBM_RETRY_AFTER_SECONDS)},
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


def _execute(
    request: LongitudinalGbmRequest,
    cancellation: CancellationContext | None = None,
    *,
    admitted: bool = False,
) -> LongitudinalGbmResult:
    acquired = admitted or _ANALYSIS_SLOTS.acquire(blocking=False)
    if not acquired:
        raise _http_error(
            429,
            "longitudinal GBM capacity is exhausted",
            **{"Retry-After": str(LONGITUDINAL_GBM_RETRY_AFTER_SECONDS)},
        )
    try:
        result = analyze_longitudinal_gbm(request, cancellation=cancellation)
    except InferenceDeadlineExceededError:
        raise _http_error(504, _TIMEOUT_MESSAGE) from None
    except InferenceCancelledError:
        raise _http_error(499, _CANCELLED_MESSAGE) from None
    except SourceProfileIntegrityError:
        raise _http_error(500, _ANALYSIS_ERROR_MESSAGE) from None
    except (LongitudinalGbmError, TypeError, ValueError, ValidationError):
        raise _http_error(
            422,
            "request could not be evaluated by the longitudinal GBM model",
        ) from None
    except Exception:  # noqa: BLE001 - sanitize unexpected failures at the boundary.
        raise _http_error(500, _ANALYSIS_ERROR_MESSAGE) from None
    finally:
        if not admitted:
            _ANALYSIS_SLOTS.release()
    if len(canonical_json_bytes(result)) > LONGITUDINAL_GBM_RESULT_MAX_BYTES:
        raise _http_error(500, "longitudinal GBM result exceeded its transport bound")
    receipt_size = len(canonical_json_bytes({"request": request, "result": result}))
    if receipt_size > LONGITUDINAL_GBM_REPLAY_MAX_BYTES:
        raise _http_error(500, "longitudinal GBM receipt exceeded its replay bound")
    return result


def _execute_verification(
    request: ReplayVerificationRequest,
    cancellation: CancellationContext | None = None,
    *,
    admitted: bool = False,
) -> ReplayVerificationResult:
    acquired = admitted or _ANALYSIS_SLOTS.acquire(blocking=False)
    if not acquired:
        raise _http_error(
            429,
            "longitudinal GBM capacity is exhausted",
            **{"Retry-After": str(LONGITUDINAL_GBM_RETRY_AFTER_SECONDS)},
        )
    try:
        result = verify_longitudinal_gbm_replay(request, cancellation=cancellation)
    except InferenceDeadlineExceededError:
        raise _http_error(504, _TIMEOUT_MESSAGE) from None
    except InferenceCancelledError:
        raise _http_error(499, _CANCELLED_MESSAGE) from None
    except SourceProfileIntegrityError:
        raise _http_error(500, _REPLAY_ERROR_MESSAGE) from None
    except (LongitudinalGbmError, TypeError, ValueError, ValidationError):
        raise _http_error(422, "replay envelope is invalid") from None
    except Exception:  # noqa: BLE001 - sanitize unexpected failures at the boundary.
        raise _http_error(500, _REPLAY_ERROR_MESSAGE) from None
    finally:
        if not admitted:
            _ANALYSIS_SLOTS.release()
    if len(canonical_json_bytes(result)) > LONGITUDINAL_GBM_RESULT_MAX_BYTES:
        raise _http_error(500, "longitudinal GBM verification exceeded its bound")
    return result


def _analysis_headers(response: Response, result: LongitudinalGbmResult) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Profile-Digest"] = result.profile_digest
    response.headers["X-GLIO-Request-Digest"] = result.request_digest
    response.headers["X-GLIO-Result-Digest"] = result.result_digest


@router.get(
    "/profile",
    response_model=LongitudinalGbmProfile,
    responses={500: _ERROR_RESPONSES[500]},
)
def profile(response: Response) -> LongitudinalGbmProfile:
    """Return the content-bound KNCC longitudinal algorithm profile."""

    try:
        result = algorithm_profile()
    except Exception:  # noqa: BLE001 - sanitize profile-integrity failures.
        raise _http_error(500, _ANALYSIS_ERROR_MESSAGE) from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Profile-Digest"] = result.profile_digest
    return result


@router.get(
    "/demo",
    response_model=LongitudinalGbmRequest,
    responses={500: _ERROR_RESPONSES[500]},
)
def demo(response: Response) -> LongitudinalGbmRequest:
    """Return a versioned synthetic primary-to-recurrent GBM series."""

    try:
        result = synthetic_demo_request()
        profile_digest = algorithm_profile().profile_digest
    except Exception:  # noqa: BLE001 - sanitize demo-integrity failures.
        raise _http_error(500, _ANALYSIS_ERROR_MESSAGE) from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Profile-Digest"] = profile_digest
    response.headers["X-GLIO-Request-Digest"] = result.request_digest
    return result


@router.post(
    "/analyze",
    response_model=LongitudinalGbmResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_request_body_schema({"$ref": "#/components/schemas/LongitudinalGbmRequest"}),
)
async def analyze(request: Request, response: Response) -> LongitudinalGbmResult:
    """Run bounded deterministic longitudinal inference off the event loop."""

    _acquire_http_slot()
    cancellation = CancellationContext.with_timeout(LONGITUDINAL_GBM_TIMEOUT_SECONDS)
    finished = asyncio.Event()
    watcher: asyncio.Task[None] | None = None
    try:
        typed = await _typed_body(
            request,
            _REQUEST_ADAPTER,
            LONGITUDINAL_GBM_REQUEST_MAX_BYTES,
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
    response_model=ReplayVerificationResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_request_body_schema(
        {"$ref": "#/components/schemas/LongitudinalGbmReplayVerificationRequest"}
    ),
)
async def verify(request: Request, response: Response) -> ReplayVerificationResult:
    """Recompute one request and verify its content-bound receipt."""

    _acquire_http_slot()
    cancellation = CancellationContext.with_timeout(LONGITUDINAL_GBM_TIMEOUT_SECONDS)
    finished = asyncio.Event()
    watcher: asyncio.Task[None] | None = None
    try:
        typed = await _typed_body(
            request,
            _REPLAY_ADAPTER,
            LONGITUDINAL_GBM_REPLAY_MAX_BYTES,
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


@m15_router.get(
    "/profile",
    response_model=M15LongitudinalRecurrenceFacadeProfile,
    responses={500: _ERROR_RESPONSES[500]},
)
def m15_profile(response: Response) -> M15LongitudinalRecurrenceFacadeProfile:
    """Describe exact M15 delegation, responsibility fit, and claim ceiling."""

    try:
        result = m15_facade_profile()
    except Exception:  # noqa: BLE001 - sanitize profile-integrity failures.
        raise _http_error(500, _ANALYSIS_ERROR_MESSAGE) from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Facade-Profile-Digest"] = result.facade_profile_digest
    response.headers["X-GLIO-Profile-Digest"] = result.delegated_profile_digest
    return result


@m15_router.get(
    "/demo",
    response_model=LongitudinalGbmRequest,
    responses={500: _ERROR_RESPONSES[500]},
)
def m15_demo(response: Response) -> LongitudinalGbmRequest:
    """Return the delegated service's exact synthetic longitudinal request."""

    result = demo(response)
    response.headers["X-GLIO-Facade-Profile-Digest"] = m15_facade_profile().facade_profile_digest
    return result


@m15_router.post(
    "/analyze",
    response_model=LongitudinalGbmResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_request_body_schema({"$ref": "#/components/schemas/LongitudinalGbmRequest"}),
)
async def m15_analyze(request: Request, response: Response) -> LongitudinalGbmResult:
    """Run the exact fitted longitudinal engine through the M15 evidence facade."""

    result = await analyze(request, response)
    response.headers["X-GLIO-Facade-Profile-Digest"] = m15_facade_profile().facade_profile_digest
    return result


@m15_router.post(
    "/verify",
    response_model=ReplayVerificationResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_request_body_schema(
        {"$ref": "#/components/schemas/LongitudinalGbmReplayVerificationRequest"}
    ),
)
async def m15_verify(request: Request, response: Response) -> ReplayVerificationResult:
    """Recompute and verify the exact delegated longitudinal receipt."""

    result = await verify(request, response)
    response.headers["X-GLIO-Facade-Profile-Digest"] = m15_facade_profile().facade_profile_digest
    return result


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
        raise LongitudinalGbmCliError(_CLI_INPUT_ERROR_MESSAGE) from None


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
    """Print the content-bound KNCC longitudinal profile."""

    try:
        result = algorithm_profile()
    except Exception:  # noqa: BLE001 - sanitize profile-integrity failures.
        raise LongitudinalGbmCliError(_ANALYSIS_ERROR_MESSAGE) from None
    _emit(result)


@cli.command("demo")
def cli_demo() -> None:
    """Print the versioned synthetic primary-to-recurrent series."""

    try:
        result = synthetic_demo_request()
    except Exception:  # noqa: BLE001 - sanitize demo-integrity failures.
        raise LongitudinalGbmCliError(_ANALYSIS_ERROR_MESSAGE) from None
    _emit(result)


@cli.command("analyze")
def cli_analyze(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Analyze one strict request without persisting it."""

    typed = _read_typed(request, _REQUEST_ADAPTER, LONGITUDINAL_GBM_REQUEST_MAX_BYTES)
    try:
        result = analyze_longitudinal_gbm(typed)
    except (LongitudinalGbmError, TypeError, ValueError, ValidationError):
        raise LongitudinalGbmCliError(_ANALYSIS_ERROR_MESSAGE) from None
    except Exception:  # noqa: BLE001 - sanitize unexpected model failures.
        raise LongitudinalGbmCliError(_ANALYSIS_ERROR_MESSAGE) from None
    if len(canonical_json_bytes(result)) > LONGITUDINAL_GBM_RESULT_MAX_BYTES:
        raise LongitudinalGbmCliError(_ANALYSIS_ERROR_MESSAGE)
    if (
        len(canonical_json_bytes({"request": typed, "result": result}))
        > LONGITUDINAL_GBM_REPLAY_MAX_BYTES
    ):
        raise LongitudinalGbmCliError(_ANALYSIS_ERROR_MESSAGE)
    _emit(result)


@cli.command("verify")
def cli_verify(
    envelope: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Replay and verify one request/result receipt."""

    typed = _read_typed(envelope, _REPLAY_ADAPTER, LONGITUDINAL_GBM_REPLAY_MAX_BYTES)
    try:
        result = verify_longitudinal_gbm_replay(typed)
    except (LongitudinalGbmError, TypeError, ValueError, ValidationError):
        raise LongitudinalGbmCliError(_REPLAY_ERROR_MESSAGE) from None
    except Exception:  # noqa: BLE001 - sanitize unexpected model failures.
        raise LongitudinalGbmCliError(_REPLAY_ERROR_MESSAGE) from None
    if len(canonical_json_bytes(result)) > LONGITUDINAL_GBM_RESULT_MAX_BYTES:
        raise LongitudinalGbmCliError(_REPLAY_ERROR_MESSAGE)
    _emit(result)
    if not result.verified:
        raise typer.Exit(code=1)


__all__ = [
    "LONGITUDINAL_GBM_MAX_CONCURRENT_ANALYSES",
    "LONGITUDINAL_GBM_REPLAY_MAX_BYTES",
    "LONGITUDINAL_GBM_REQUEST_MAX_BYTES",
    "LONGITUDINAL_GBM_RESULT_MAX_BYTES",
    "LONGITUDINAL_GBM_ROUTE_PREFIX",
    "LONGITUDINAL_GBM_TIMEOUT_SECONDS",
    "M15_LONGITUDINAL_RECURRENCE_ROUTE_PREFIX",
    "LongitudinalGbmCliError",
    "cli",
    "install_longitudinal_gbm_openapi",
    "m15_router",
    "router",
]

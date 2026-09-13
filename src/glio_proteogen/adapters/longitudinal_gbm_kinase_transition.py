"""Bounded HTTP/CLI boundary for longitudinal signature-transition concordance."""

from __future__ import annotations

import asyncio
import sys
from functools import partial
from pathlib import Path  # noqa: TC003 - Typer resolves annotations at runtime.
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
from glio_proteogen.research.longitudinal_gbm_kinase_transition.contracts import (
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    LongitudinalGbmKinaseTransitionProfile,
    LongitudinalGbmKinaseTransitionRequest,
    LongitudinalGbmKinaseTransitionResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.demo import (
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.errors import (
    LongitudinalGbmKinaseTransitionError,
    SourceProfileIntegrityError,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.profile import (
    algorithm_profile,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.service import (
    analyze_longitudinal_gbm_kinase_transition,
    verify_longitudinal_gbm_kinase_transition_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

LONGITUDINAL_GBM_KINASE_TRANSITION_ROUTE_PREFIX: Final = (
    "/v1/research/longitudinal-gbm-kinase-transition"
)
LONGITUDINAL_GBM_KINASE_TRANSITION_REQUEST_MAX_BYTES: Final = MAX_REQUEST_BYTES
LONGITUDINAL_GBM_KINASE_TRANSITION_RESULT_MAX_BYTES: Final = MAX_RESULT_BYTES
LONGITUDINAL_GBM_KINASE_TRANSITION_REPLAY_MAX_BYTES: Final = MAX_REPLAY_BYTES
LONGITUDINAL_GBM_KINASE_TRANSITION_MAX_CONCURRENT_ANALYSES: Final = 2
LONGITUDINAL_GBM_KINASE_TRANSITION_TIMEOUT_SECONDS: Final = 120.0
_DISCONNECT_POLL_SECONDS: Final = 0.05
_CLI_INPUT_ERROR: Final = "input does not satisfy the kinase-transition contract"
_CLI_ANALYSIS_ERROR: Final = "kinase-transition concordance analysis failed safely"
_CLI_REPLAY_ERROR: Final = "kinase-transition concordance replay failed safely"
_CLI_RESULT_SIZE_ERROR: Final = "kinase-transition result exceeded its bound"
_REQUEST_ADAPTER: Final = TypeAdapter(LongitudinalGbmKinaseTransitionRequest)
_REPLAY_ADAPTER: Final = TypeAdapter(ReplayVerificationRequest)
_SLOTS = BoundedSemaphore(LONGITUDINAL_GBM_KINASE_TRANSITION_MAX_CONCURRENT_ANALYSES)

router = APIRouter(
    prefix=LONGITUDINAL_GBM_KINASE_TRANSITION_ROUTE_PREFIX,
    tags=["research-longitudinal-gbm-kinase-transition"],
)
cli = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Run research-only longitudinal SPHINKS signature-transition concordance.",
)


class LongitudinalGbmKinaseTransitionCliError(typer.BadParameter):
    """Sanitized signature-transition command-line error."""


def _http_error(status: int, detail: str, **headers: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=detail,
        headers={"Cache-Control": "no-store", **headers},
    )


async def _bounded_body(request: Request, maximum: int) -> bytes:
    raw_length = request.headers.get("content-length")
    if raw_length is not None:
        try:
            declared = int(raw_length)
        except ValueError:
            raise _http_error(400, "invalid content-length") from None
        if declared < 0:
            raise _http_error(400, "invalid content-length")
        if declared > maximum:
            raise _http_error(413, "request body exceeds the byte limit")
    chunks: list[bytes] = []
    received = 0
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > maximum:
                raise _http_error(413, "request body exceeds the byte limit")
            chunks.append(chunk)
    except ClientDisconnect:
        raise _http_error(499, "kinase-transition computation was cancelled") from None
    return b"".join(chunks)


def _decode[T](payload: bytes, adapter: TypeAdapter[T], maximum: int) -> T:
    strict_json_loads(payload, max_bytes=maximum)
    return adapter.validate_json(payload, strict=True)


async def _typed_body[T](
    request: Request,
    adapter: TypeAdapter[T],
    maximum: int,
    cancellation: CancellationContext,
) -> T:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise _http_error(415, "content-type must be application/json")
    try:
        async with asyncio.timeout(cancellation.remaining_seconds()):
            body = await _bounded_body(request, maximum)
        cancellation.checkpoint()
        typed = await anyio.to_thread.run_sync(partial(_decode, body, adapter, maximum))
        cancellation.checkpoint()
    except TimeoutError:
        raise _http_error(504, "kinase-transition computation timed out") from None
    except InferenceDeadlineExceededError:
        raise _http_error(504, "kinase-transition computation timed out") from None
    except InferenceCancelledError:
        raise _http_error(499, "kinase-transition computation was cancelled") from None
    except (StrictJsonError, ValidationError):
        raise _http_error(422, "request does not satisfy the kinase-transition contract") from None
    else:
        return typed


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


def _acquire_slot() -> None:
    if not _SLOTS.acquire(blocking=False):
        raise _http_error(
            429,
            "kinase-transition execution capacity is exhausted",
            **{"Retry-After": "1"},
        )


def _execute(
    request: LongitudinalGbmKinaseTransitionRequest,
    cancellation: CancellationContext,
) -> LongitudinalGbmKinaseTransitionResult:
    try:
        result = analyze_longitudinal_gbm_kinase_transition(request, cancellation=cancellation)
    except InferenceDeadlineExceededError:
        raise _http_error(504, "kinase-transition computation timed out") from None
    except InferenceCancelledError:
        raise _http_error(499, "kinase-transition computation was cancelled") from None
    except SourceProfileIntegrityError:
        raise _http_error(500, "kinase-transition analysis failed safely") from None
    except (LongitudinalGbmKinaseTransitionError, TypeError, ValueError, ValidationError):
        raise _http_error(422, "request could not be evaluated by the signature model") from None
    except Exception:  # noqa: BLE001 - sanitize unexpected numerical failures.
        raise _http_error(500, "kinase-transition analysis failed safely") from None
    if len(canonical_json_bytes(result)) > LONGITUDINAL_GBM_KINASE_TRANSITION_RESULT_MAX_BYTES:
        raise _http_error(500, "kinase-transition result exceeded its bound")
    if (
        len(canonical_json_bytes({"request": request, "result": result}))
        > LONGITUDINAL_GBM_KINASE_TRANSITION_REPLAY_MAX_BYTES
    ):
        raise _http_error(500, "kinase-transition receipt exceeded its bound")
    return result


def _execute_verification(
    request: ReplayVerificationRequest,
    cancellation: CancellationContext,
) -> ReplayVerificationResult:
    try:
        result = verify_longitudinal_gbm_kinase_transition_replay(
            request, cancellation=cancellation
        )
    except InferenceDeadlineExceededError:
        raise _http_error(504, "kinase-transition replay timed out") from None
    except InferenceCancelledError:
        raise _http_error(499, "kinase-transition replay was cancelled") from None
    except SourceProfileIntegrityError:
        raise _http_error(500, "kinase-transition replay failed safely") from None
    except (LongitudinalGbmKinaseTransitionError, TypeError, ValueError, ValidationError):
        raise _http_error(422, "replay envelope is invalid") from None
    except Exception:  # noqa: BLE001 - sanitize unexpected replay failures.
        raise _http_error(500, "kinase-transition replay failed safely") from None
    if len(canonical_json_bytes(result)) > LONGITUDINAL_GBM_KINASE_TRANSITION_RESULT_MAX_BYTES:
        raise _http_error(500, "kinase-transition verification exceeded its bound")
    return result


_ERROR_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    code: {
        "description": description,
        "content": {"application/json": {"schema": {"type": "object"}}},
    }
    for code, description in {
        400: "Invalid transport metadata",
        413: "Request body exceeds the byte limit",
        415: "Unsupported request media type",
        422: "Request is not evaluable",
        429: "Research execution capacity exhausted",
        499: "Caller disconnected or cancelled",
        500: "Sanitized internal failure",
        504: "Research execution deadline exceeded",
    }.items()
}


def _body_schema(reference: str) -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"$ref": reference}}},
        }
    }


def install_longitudinal_gbm_kinase_transition_openapi(app: FastAPI) -> None:
    original_openapi = app.openapi
    replay_schema = _REPLAY_ADAPTER.json_schema(ref_template="#/components/schemas/{model}")
    definitions = replay_schema.pop("$defs")

    def openapi_with_replay() -> dict[str, Any]:
        schema = original_openapi()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, definition in definitions.items():
            components.setdefault(name, definition)
        name = "LongitudinalGbmKinaseTransitionReplayVerificationRequest"
        components[name] = replay_schema
        operation = schema["paths"][f"{LONGITUDINAL_GBM_KINASE_TRANSITION_ROUTE_PREFIX}/verify"][
            "post"
        ]
        operation["requestBody"] = {
            "required": True,
            "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{name}"}}},
        }
        app.openapi_schema = schema
        return schema

    app.__dict__["openapi"] = openapi_with_replay


@router.get("/profile", response_model=LongitudinalGbmKinaseTransitionProfile)
def profile(response: Response) -> LongitudinalGbmKinaseTransitionProfile:
    try:
        result = algorithm_profile()
    except Exception:  # noqa: BLE001 - sanitize source/profile integrity failures.
        raise _http_error(500, "kinase-transition profile failed safely") from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Profile-Digest"] = result.profile_digest
    return result


@router.get("/demo", response_model=LongitudinalGbmKinaseTransitionRequest)
def demo(response: Response) -> LongitudinalGbmKinaseTransitionRequest:
    try:
        result = synthetic_demo_request()
        profile_digest = algorithm_profile().profile_digest
    except Exception:  # noqa: BLE001 - sanitize demo/source integrity failures.
        raise _http_error(500, "kinase-transition demo failed safely") from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Profile-Digest"] = profile_digest
    response.headers["X-GLIO-Request-Digest"] = result.request_digest
    return result


@router.post(
    "/analyze",
    response_model=LongitudinalGbmKinaseTransitionResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_body_schema("#/components/schemas/LongitudinalGbmKinaseTransitionRequest"),
)
async def analyze(request: Request, response: Response) -> LongitudinalGbmKinaseTransitionResult:
    _acquire_slot()
    cancellation = CancellationContext.with_timeout(
        LONGITUDINAL_GBM_KINASE_TRANSITION_TIMEOUT_SECONDS
    )
    finished = asyncio.Event()
    watcher: asyncio.Task[None] | None = None
    try:
        typed = await _typed_body(
            request,
            _REQUEST_ADAPTER,
            LONGITUDINAL_GBM_KINASE_TRANSITION_REQUEST_MAX_BYTES,
            cancellation,
        )
        watcher = asyncio.create_task(_watch_disconnect(request, cancellation, finished))
        result = await anyio.to_thread.run_sync(partial(_execute, typed, cancellation))
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-GLIO-Profile-Digest"] = result.profile_digest
        response.headers["X-GLIO-Request-Digest"] = result.request_digest
        response.headers["X-GLIO-Result-Digest"] = result.result_digest
        return result
    finally:
        finished.set()
        if watcher is not None:
            await watcher
        _SLOTS.release()


@router.post(
    "/verify",
    response_model=ReplayVerificationResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_body_schema(
        "#/components/schemas/LongitudinalGbmKinaseTransitionReplayVerificationRequest"
    ),
)
async def verify(request: Request, response: Response) -> ReplayVerificationResult:
    _acquire_slot()
    cancellation = CancellationContext.with_timeout(
        LONGITUDINAL_GBM_KINASE_TRANSITION_TIMEOUT_SECONDS
    )
    finished = asyncio.Event()
    watcher: asyncio.Task[None] | None = None
    try:
        typed = await _typed_body(
            request,
            _REPLAY_ADAPTER,
            LONGITUDINAL_GBM_KINASE_TRANSITION_REPLAY_MAX_BYTES,
            cancellation,
        )
        watcher = asyncio.create_task(_watch_disconnect(request, cancellation, finished))
        result = await anyio.to_thread.run_sync(partial(_execute_verification, typed, cancellation))
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-GLIO-Profile-Digest"] = algorithm_profile().profile_digest
        response.headers["X-GLIO-Request-Digest"] = result.recomputed_request_digest
        response.headers["X-GLIO-Result-Digest"] = result.recomputed_result_digest
        return result
    finally:
        finished.set()
        if watcher is not None:
            await watcher
        _SLOTS.release()


def _read_typed[T](path: Path, adapter: TypeAdapter[T], maximum: int) -> T:
    try:
        data = read_bounded(path, maximum)
        strict_json_loads(data, max_bytes=maximum)
        return adapter.validate_json(data, strict=True)
    except (OSError, RequestBodyTooLargeError, StrictJsonError, ValueError, ValidationError):
        raise LongitudinalGbmKinaseTransitionCliError(_CLI_INPUT_ERROR) from None


def _emit(value: object) -> None:
    payload = canonical_json_bytes(value) + b"\n"
    binary = getattr(sys.stdout, "buffer", None)
    if binary is None:
        typer.echo(payload.decode("utf-8"))
    else:
        binary.write(payload)
        binary.flush()


@cli.command("profile")
def cli_profile() -> None:
    try:
        result = algorithm_profile()
    except Exception:  # noqa: BLE001 - sanitize profile failures at the CLI boundary.
        raise LongitudinalGbmKinaseTransitionCliError(_CLI_ANALYSIS_ERROR) from None
    _emit(result)


@cli.command("demo")
def cli_demo() -> None:
    try:
        result = synthetic_demo_request()
    except Exception:  # noqa: BLE001 - sanitize demo failures at the CLI boundary.
        raise LongitudinalGbmKinaseTransitionCliError(_CLI_ANALYSIS_ERROR) from None
    _emit(result)


@cli.command("analyze")
def cli_analyze(request: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    typed = _read_typed(
        request,
        _REQUEST_ADAPTER,
        LONGITUDINAL_GBM_KINASE_TRANSITION_REQUEST_MAX_BYTES,
    )
    try:
        result = analyze_longitudinal_gbm_kinase_transition(typed)
    except Exception:  # noqa: BLE001 - sanitize analysis failures at the CLI boundary.
        raise LongitudinalGbmKinaseTransitionCliError(_CLI_ANALYSIS_ERROR) from None
    if len(canonical_json_bytes(result)) > LONGITUDINAL_GBM_KINASE_TRANSITION_RESULT_MAX_BYTES:
        raise LongitudinalGbmKinaseTransitionCliError(_CLI_RESULT_SIZE_ERROR)
    _emit(result)


@cli.command("verify")
def cli_verify(envelope: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    typed = _read_typed(
        envelope,
        _REPLAY_ADAPTER,
        LONGITUDINAL_GBM_KINASE_TRANSITION_REPLAY_MAX_BYTES,
    )
    try:
        result = verify_longitudinal_gbm_kinase_transition_replay(typed)
    except Exception:  # noqa: BLE001 - sanitize replay failures at the CLI boundary.
        raise LongitudinalGbmKinaseTransitionCliError(_CLI_REPLAY_ERROR) from None
    _emit(result)
    if not result.verified:
        raise typer.Exit(code=1)


__all__ = [
    "LONGITUDINAL_GBM_KINASE_TRANSITION_MAX_CONCURRENT_ANALYSES",
    "LONGITUDINAL_GBM_KINASE_TRANSITION_REPLAY_MAX_BYTES",
    "LONGITUDINAL_GBM_KINASE_TRANSITION_REQUEST_MAX_BYTES",
    "LONGITUDINAL_GBM_KINASE_TRANSITION_RESULT_MAX_BYTES",
    "LONGITUDINAL_GBM_KINASE_TRANSITION_ROUTE_PREFIX",
    "LONGITUDINAL_GBM_KINASE_TRANSITION_TIMEOUT_SECONDS",
    "LongitudinalGbmKinaseTransitionCliError",
    "cli",
    "install_longitudinal_gbm_kinase_transition_openapi",
    "router",
]

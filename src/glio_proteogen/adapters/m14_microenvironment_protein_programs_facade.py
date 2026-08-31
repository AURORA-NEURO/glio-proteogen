"""Isolated HTTP facade for exact M14 bulk protein-program evidence."""

from __future__ import annotations

import asyncio
from functools import partial
from threading import BoundedSemaphore
from typing import TYPE_CHECKING, Any, Final

import anyio
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import TypeAdapter, ValidationError
from starlette.requests import ClientDisconnect

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.research.m14_microenvironment_protein_programs_facade import (
    DEMO_ID,
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    ROUTE_PREFIX,
    M14MicroenvironmentProteinProgramsFacadeProfile,
    ProteinProgramRequest,
    ProteinProgramResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
    analyze_m14_microenvironment_program_evidence,
    m14_facade_demo,
    m14_facade_profile,
    verify_m14_microenvironment_program_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_ROUTE_PREFIX: Final = ROUTE_PREFIX
M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REQUEST_MAX_BYTES: Final = MAX_REQUEST_BYTES
M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_RESULT_MAX_BYTES: Final = MAX_RESULT_BYTES
M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REPLAY_MAX_BYTES: Final = MAX_REPLAY_BYTES
M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_DEMO_ID: Final = DEMO_ID
M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_MAX_CONCURRENT_ANALYSES: Final = 2
M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_TIMEOUT_SECONDS: Final = 25.0
_DISCONNECT_POLL_SECONDS: Final = 0.05

_REQUEST_ADAPTER: Final = TypeAdapter(ProteinProgramRequest)
_REPLAY_ADAPTER: Final = TypeAdapter(ReplayVerificationRequest)
_REQUEST_SCHEMA: Final = _REQUEST_ADAPTER.json_schema(ref_template="#/components/schemas/{model}")
_REQUEST_DEFINITIONS: Final = _REQUEST_SCHEMA.pop("$defs")
_REPLAY_SCHEMA: Final = _REPLAY_ADAPTER.json_schema(ref_template="#/components/schemas/{model}")
_REPLAY_DEFINITIONS: Final = _REPLAY_SCHEMA.pop("$defs")
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
_EXECUTION_SLOTS = BoundedSemaphore(M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_MAX_CONCURRENT_ANALYSES)

_INVALID_REQUEST = "request does not satisfy the M14 bulk protein-program evidence contract"
_ANALYSIS_FAILURE = "M14 bulk protein-program evidence analysis failed safely"
_REPLAY_FAILURE = "M14 bulk protein-program evidence replay failed safely"
_PROFILE_FAILURE = "M14 bulk protein-program evidence profile is unavailable"
_DEMO_FAILURE = "M14 bulk protein-program evidence demo is unavailable"
_TIMEOUT_FAILURE = "M14 bulk protein-program evidence computation exceeded its deadline"
_CANCELLED_FAILURE = "M14 bulk protein-program evidence computation was cancelled"

router = APIRouter(
    prefix=M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_ROUTE_PREFIX,
    tags=["research-m14-microenvironment-protein-program-evidence"],
)


def _http_error(status_code: int, detail: str, **headers: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={"Cache-Control": "no-store", **headers},
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


async def _bounded_json_body(request: Request, max_bytes: int) -> bytes:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise _http_error(415, "content-type must be application/json")
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
        raise _http_error(499, _CANCELLED_FAILURE) from None
    body = b"".join(chunks)
    try:
        strict_json_loads(body, max_bytes=max_bytes)
    except StrictJsonError:
        raise _http_error(422, _INVALID_REQUEST) from None
    return body


async def _typed_body[T](
    request: Request,
    adapter: TypeAdapter[T],
    max_bytes: int,
) -> T:
    body = await _bounded_json_body(request, max_bytes)
    try:
        return adapter.validate_json(body, strict=True)
    except ValidationError:
        raise _http_error(422, _INVALID_REQUEST) from None


def _admit() -> None:
    if not _EXECUTION_SLOTS.acquire(blocking=False):
        raise _http_error(
            429,
            "M14 bulk protein-program evidence capacity is exhausted",
            **{"Retry-After": "1"},
        )


def _bounded_result[T](value: T) -> T:
    if len(canonical_json_bytes(value)) > M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_RESULT_MAX_BYTES:
        raise _http_error(500, "M14 bulk protein-program response exceeded its byte limit")
    return value


def _bounded_demo(value: ProteinProgramRequest) -> ProteinProgramRequest:
    if len(canonical_json_bytes(value)) > M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REQUEST_MAX_BYTES:
        raise _http_error(500, _DEMO_FAILURE)
    return value


def _bounded_receipt(
    request: ProteinProgramRequest,
    result: ProteinProgramResult,
) -> ProteinProgramResult:
    if (
        len(canonical_json_bytes({"request": request, "result": result}))
        > M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REPLAY_MAX_BYTES
    ):
        raise _http_error(500, "M14 bulk protein-program receipt exceeded its byte limit")
    return result


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


def _execute_analysis(
    request: ProteinProgramRequest,
    cancellation: CancellationContext,
) -> ProteinProgramResult:
    try:
        result = analyze_m14_microenvironment_program_evidence(
            request,
            cancellation=cancellation,
        )
    except InferenceDeadlineExceededError:
        raise _http_error(504, _TIMEOUT_FAILURE) from None
    except InferenceCancelledError:
        raise _http_error(499, _CANCELLED_FAILURE) from None
    except (TypeError, ValueError, ValidationError):
        raise _http_error(422, _INVALID_REQUEST) from None
    except Exception:  # noqa: BLE001 - boundary must not expose model internals.
        raise _http_error(500, _ANALYSIS_FAILURE) from None
    return _bounded_receipt(request, _bounded_result(result))


def _execute_replay(
    request: ReplayVerificationRequest,
    cancellation: CancellationContext,
) -> ReplayVerificationResult:
    try:
        result = verify_m14_microenvironment_program_replay(
            request,
            cancellation=cancellation,
        )
    except InferenceDeadlineExceededError:
        raise _http_error(504, _TIMEOUT_FAILURE) from None
    except InferenceCancelledError:
        raise _http_error(499, _CANCELLED_FAILURE) from None
    except (TypeError, ValueError, ValidationError):
        raise _http_error(422, _INVALID_REQUEST) from None
    except Exception:  # noqa: BLE001 - boundary must not expose replay internals.
        raise _http_error(500, _REPLAY_FAILURE) from None
    return _bounded_result(result)


def _request_body_schema(schema: dict[str, Any]) -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": schema}},
        }
    }


def install_m14_microenvironment_protein_programs_openapi(app: FastAPI) -> None:
    """Register strict raw-body request contracts in a containing FastAPI app."""

    original_openapi = app.openapi

    def openapi_with_facade_contracts() -> dict[str, Any]:
        schema = original_openapi()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, definition in {**_REQUEST_DEFINITIONS, **_REPLAY_DEFINITIONS}.items():
            components.setdefault(name, definition)
        components["ProteinProgramRequest"] = _REQUEST_SCHEMA
        components["M14MicroenvironmentReplayVerificationRequest"] = _REPLAY_SCHEMA
        for operation, component in (
            ("analyze", "ProteinProgramRequest"),
            ("verify", "M14MicroenvironmentReplayVerificationRequest"),
        ):
            schema["paths"][f"{M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_ROUTE_PREFIX}/{operation}"][
                "post"
            ]["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{component}"}}
                },
            }
        app.openapi_schema = schema
        return schema

    app.__dict__["openapi"] = openapi_with_facade_contracts


def _set_result_headers(response: Response, result: ProteinProgramResult) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Facade-Profile-Digest"] = m14_facade_profile().facade_profile_digest
    response.headers["X-GLIO-Profile-Digest"] = result.profile_digest
    response.headers["X-GLIO-Request-Digest"] = result.request_digest
    response.headers["X-GLIO-Result-Digest"] = result.result_digest


@router.get("/profile", response_model=M14MicroenvironmentProteinProgramsFacadeProfile)
def profile(response: Response) -> M14MicroenvironmentProteinProgramsFacadeProfile:
    """Describe exact delegation, M14 evidence fit, and the claim ceiling."""

    try:
        result = _bounded_result(m14_facade_profile())
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - public profile failure remains sanitized.
        raise _http_error(500, _PROFILE_FAILURE) from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Facade-Profile-Digest"] = result.facade_profile_digest
    response.headers["X-GLIO-Profile-Digest"] = result.delegated_profile_digest
    return result


@router.get("/demo", response_model=ProteinProgramRequest)
def demo(response: Response) -> ProteinProgramRequest:
    """Return the delegated service's exact synthetic bulk-protein request."""

    try:
        result = _bounded_demo(m14_facade_demo())
        facade_profile = m14_facade_profile()
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - public demo failure remains sanitized.
        raise _http_error(500, _DEMO_FAILURE) from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Facade-Profile-Digest"] = facade_profile.facade_profile_digest
    response.headers["X-GLIO-Profile-Digest"] = facade_profile.delegated_profile_digest
    response.headers["X-GLIO-Request-Digest"] = result.request_digest
    return result


@router.post(
    "/analyze",
    response_model=ProteinProgramResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_request_body_schema({"$ref": "#/components/schemas/ProteinProgramRequest"}),
)
async def analyze(request: Request, response: Response) -> ProteinProgramResult:
    """Run exact bulk protein-program inference through strict bounded ingress."""

    _admit()
    cancellation = CancellationContext.with_timeout(
        M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_TIMEOUT_SECONDS
    )
    finished = asyncio.Event()
    watcher: asyncio.Task[None] | None = None
    try:
        typed = await _typed_body(
            request,
            _REQUEST_ADAPTER,
            M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REQUEST_MAX_BYTES,
        )
        watcher = asyncio.create_task(_watch_disconnect(request, cancellation, finished))
        result = await anyio.to_thread.run_sync(partial(_execute_analysis, typed, cancellation))
        _set_result_headers(response, result)
        return result
    finally:
        try:
            await _close_watcher(finished, watcher)
        finally:
            _EXECUTION_SLOTS.release()


@router.post(
    "/verify",
    response_model=ReplayVerificationResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_request_body_schema(
        {"$ref": "#/components/schemas/M14MicroenvironmentReplayVerificationRequest"}
    ),
)
async def verify(request: Request, response: Response) -> ReplayVerificationResult:
    """Recompute and verify the exact delegated request/result receipt."""

    _admit()
    cancellation = CancellationContext.with_timeout(
        M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_TIMEOUT_SECONDS
    )
    finished = asyncio.Event()
    watcher: asyncio.Task[None] | None = None
    try:
        typed = await _typed_body(
            request,
            _REPLAY_ADAPTER,
            M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REPLAY_MAX_BYTES,
        )
        watcher = asyncio.create_task(_watch_disconnect(request, cancellation, finished))
        result = await anyio.to_thread.run_sync(partial(_execute_replay, typed, cancellation))
        response.headers["Cache-Control"] = "no-store"
        facade_profile = m14_facade_profile()
        response.headers["X-GLIO-Facade-Profile-Digest"] = facade_profile.facade_profile_digest
        response.headers["X-GLIO-Profile-Digest"] = facade_profile.delegated_profile_digest
        response.headers["X-GLIO-Request-Digest"] = result.recomputed_request_digest
        response.headers["X-GLIO-Result-Digest"] = result.recomputed_result_digest
        return result
    finally:
        try:
            await _close_watcher(finished, watcher)
        finally:
            _EXECUTION_SLOTS.release()


__all__ = [
    "M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_DEMO_ID",
    "M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_MAX_CONCURRENT_ANALYSES",
    "M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REPLAY_MAX_BYTES",
    "M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_REQUEST_MAX_BYTES",
    "M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_RESULT_MAX_BYTES",
    "M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_ROUTE_PREFIX",
    "M14_MICROENVIRONMENT_PROTEIN_PROGRAMS_TIMEOUT_SECONDS",
    "install_m14_microenvironment_protein_programs_openapi",
    "router",
]

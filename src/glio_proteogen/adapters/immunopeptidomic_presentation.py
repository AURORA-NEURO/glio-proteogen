"""Stateless research HTTP/CLI adapter for caller-owned HLA presentation."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves this annotation.
from typing import Annotated, Final

import typer
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.research.immunopeptidomic_presentation import (
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    ImmunopeptidomicInputError,
    ImmunopeptidomicPresentationRequest,
    ImmunopeptidomicPresentationResult,
    PresentationProfile,
    PresentationReplayRequest,
    PresentationReplayResult,
    analyze_immunopeptidomic_presentation,
    presentation_profile,
    synthetic_presentation_request,
    verify_presentation_replay,
)

PRESENTATION_ROUTE_PREFIX: Final = "/v1/research/immunopeptidomic-presentation"
PRESENTATION_REQUEST_MAX_BYTES: Final = MAX_REQUEST_BYTES
PRESENTATION_RESULT_MAX_BYTES: Final = MAX_RESULT_BYTES
PRESENTATION_REPLAY_MAX_BYTES: Final = MAX_REQUEST_BYTES + MAX_RESULT_BYTES
_REQUEST_ADAPTER: Final = TypeAdapter(ImmunopeptidomicPresentationRequest)
_REPLAY_ADAPTER: Final = TypeAdapter(PresentationReplayRequest)
_REQUEST_SCHEMA: Final = _REQUEST_ADAPTER.json_schema()
_REPLAY_SCHEMA: Final = _REPLAY_ADAPTER.json_schema()
_REQUEST_ERROR: Final = "request does not satisfy the immunopeptidomic presentation contract"
_RESULT_ERROR: Final = "presentation analysis failed safely"
_REPLAY_ERROR: Final = "presentation replay failed safely"

router = APIRouter(prefix=PRESENTATION_ROUTE_PREFIX, tags=["research-immunopeptidomic"])
cli = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Run caller-owned, research-only glioma immunopeptidomic scoring.",
)


def _request_body_schema(schema: dict[str, object]) -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": schema}},
        }
    }


def _error(status: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=message,
        headers={"Cache-Control": "no-store"},
    )


async def _typed_body[T](request: Request, adapter: TypeAdapter[T], max_bytes: int) -> T:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise _error(415, "content-type must be application/json")
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            declared_bytes = int(declared)
        except ValueError:
            raise _error(400, "invalid content-length") from None
        if declared_bytes < 0:
            raise _error(400, "invalid content-length")
        if declared_bytes > max_bytes:
            raise _error(413, "request body exceeds the byte limit")
    body = await request.body()
    if len(body) > max_bytes:
        raise _error(413, "request body exceeds the byte limit")
    try:
        strict_json_loads(body, max_bytes=max_bytes)
        return adapter.validate_json(body, strict=True)
    except (StrictJsonError, ValidationError):
        raise _error(422, _REQUEST_ERROR) from None


def _headers(
    response: Response,
    *,
    profile_digest: str,
    request_digest: str | None = None,
    result_digest: str | None = None,
) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Profile-Digest"] = profile_digest
    if request_digest is not None:
        response.headers["X-GLIO-Request-Digest"] = request_digest
    if result_digest is not None:
        response.headers["X-GLIO-Result-Digest"] = result_digest


def ensure_presentation_ready() -> PresentationProfile:
    """Return the immutable profile used for readiness admission."""
    return presentation_profile()


@router.get("/profile", response_model=PresentationProfile)
def profile(response: Response) -> PresentationProfile:
    result = presentation_profile()
    _headers(response, profile_digest=result.profile_digest)
    return result


@router.get("/demo", response_model=ImmunopeptidomicPresentationRequest)
def demo(response: Response) -> ImmunopeptidomicPresentationRequest:
    result = synthetic_presentation_request()
    _headers(
        response,
        profile_digest=presentation_profile().profile_digest,
        request_digest=result.request_digest,
    )
    return result


@router.post(
    "/analyze",
    response_model=ImmunopeptidomicPresentationResult,
    openapi_extra=_request_body_schema(_REQUEST_SCHEMA),
)
async def analyze(request: Request, response: Response) -> ImmunopeptidomicPresentationResult:
    typed = await _typed_body(request, _REQUEST_ADAPTER, PRESENTATION_REQUEST_MAX_BYTES)
    try:
        result = analyze_immunopeptidomic_presentation(typed)
    except (ImmunopeptidomicInputError, TypeError, ValueError):
        raise _error(422, _RESULT_ERROR) from None
    if len(canonical_json_bytes(result)) > PRESENTATION_RESULT_MAX_BYTES:
        raise _error(500, "presentation result exceeded the byte limit")
    _headers(
        response,
        profile_digest=result.profile_digest,
        request_digest=result.request_digest,
        result_digest=result.result_digest,
    )
    return result


@router.post(
    "/verify",
    response_model=PresentationReplayResult,
    openapi_extra=_request_body_schema(_REPLAY_SCHEMA),
)
async def verify(request: Request, response: Response) -> PresentationReplayResult:
    envelope = await _typed_body(request, _REPLAY_ADAPTER, PRESENTATION_REPLAY_MAX_BYTES)
    try:
        verify_presentation_replay(envelope.request, envelope.result)
    except (ImmunopeptidomicInputError, TypeError, ValueError):
        raise _error(422, _REPLAY_ERROR) from None
    result = PresentationReplayResult(
        request_digest=envelope.request.request_digest,
        result_digest=envelope.result.result_digest,
    )
    _headers(
        response,
        profile_digest=presentation_profile().profile_digest,
        request_digest=result.request_digest,
        result_digest=result.result_digest,
    )
    return result


def _read_typed[T](path: Path, adapter: TypeAdapter[T], max_bytes: int) -> T:
    try:
        body = read_bounded(path, max_bytes)
        strict_json_loads(body, max_bytes=max_bytes)
        return adapter.validate_json(body, strict=True)
    except (OSError, RequestBodyTooLargeError, StrictJsonError, ValidationError):
        raise typer.BadParameter(_REQUEST_ERROR) from None


def _write_new(path: Path, payload: object) -> None:
    if path.exists():
        raise typer.BadParameter("output already exists; refusing overwrite")  # noqa: TRY003
    path.write_bytes(canonical_json_bytes(payload) + b"\n")


@cli.command("profile")
def cli_profile() -> None:
    typer.echo(canonical_json_bytes(presentation_profile()).decode())


@cli.command("demo")
def cli_demo() -> None:
    typer.echo(canonical_json_bytes(synthetic_presentation_request()).decode())


@cli.command("analyze")
def cli_analyze(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    typed = _read_typed(request, _REQUEST_ADAPTER, PRESENTATION_REQUEST_MAX_BYTES)
    try:
        result = analyze_immunopeptidomic_presentation(typed)
    except (ImmunopeptidomicInputError, TypeError, ValueError) as error:
        raise typer.BadParameter(_RESULT_ERROR) from error
    if output is None:
        typer.echo(canonical_json_bytes(result).decode())
    else:
        _write_new(output, result)


@cli.command("verify")
def cli_verify(
    envelope: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    typed = _read_typed(envelope, _REPLAY_ADAPTER, PRESENTATION_REPLAY_MAX_BYTES)
    try:
        verify_presentation_replay(typed.request, typed.result)
    except (ImmunopeptidomicInputError, TypeError, ValueError) as error:
        raise typer.BadParameter(_REPLAY_ERROR) from error
    typer.echo(
        json.dumps(
            {
                "verified": True,
                "request_digest": typed.request.request_digest,
                "result_digest": typed.result.result_digest,
            }
        )
    )


__all__ = [
    "PRESENTATION_REPLAY_MAX_BYTES",
    "PRESENTATION_REQUEST_MAX_BYTES",
    "PRESENTATION_RESULT_MAX_BYTES",
    "PRESENTATION_ROUTE_PREFIX",
    "cli",
    "demo",
    "ensure_presentation_ready",
    "profile",
    "router",
    "verify",
]

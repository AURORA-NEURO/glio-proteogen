"""HTTP and CLI adapter for the Neftel-to-ECGI GBM microenvironment bridge."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - Typer resolves this annotation.
from typing import Annotated, Final

import typer
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.research.gbm_microenvironment_graph import (
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    MicroenvironmentGraphProfile,
    MicroenvironmentGraphReplayRequest,
    MicroenvironmentGraphReplayResult,
    MicroenvironmentGraphRequest,
    MicroenvironmentGraphResult,
    analyze_microenvironment_graph,
    microenvironment_graph_profile,
    synthetic_microenvironment_graph_request,
    verify_microenvironment_graph_replay,
)

MICROENVIRONMENT_GRAPH_ROUTE_PREFIX: Final = "/v1/research/gbm-microenvironment-graph"
MICROENVIRONMENT_GRAPH_REQUEST_MAX_BYTES: Final = MAX_REQUEST_BYTES
MICROENVIRONMENT_GRAPH_RESULT_MAX_BYTES: Final = MAX_RESULT_BYTES
MICROENVIRONMENT_GRAPH_REPLAY_MAX_BYTES: Final = MAX_REPLAY_BYTES
_REQUEST_ADAPTER: Final = TypeAdapter(MicroenvironmentGraphRequest)
_REPLAY_ADAPTER: Final = TypeAdapter(MicroenvironmentGraphReplayRequest)
_REQUEST_ERROR: Final = "request does not satisfy the GBM microenvironment graph contract"
_RESULT_ERROR: Final = "GBM microenvironment graph analysis failed safely"
_REPLAY_ERROR: Final = "GBM microenvironment graph replay failed safely"
_OUTPUT_EXISTS_ERROR: Final = "output already exists; refusing overwrite"

router = APIRouter(
    prefix=MICROENVIRONMENT_GRAPH_ROUTE_PREFIX,
    tags=["research-gbm-microenvironment"],
)
cli = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Run source-locked Neftel protein evidence through a GBM state graph.",
)


def _error(status: int, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail=message, headers={"Cache-Control": "no-store"})


async def _typed_body[T](request: Request, adapter: TypeAdapter[T], maximum: int) -> T:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise _error(415, "content-type must be application/json")
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > maximum:
                raise _error(413, "request body exceeds the byte limit")
        except ValueError:
            raise _error(400, "invalid content-length") from None
    body = await request.body()
    if len(body) > maximum:
        raise _error(413, "request body exceeds the byte limit")
    try:
        strict_json_loads(body, max_bytes=maximum)
        return adapter.validate_json(body, strict=True)
    except (StrictJsonError, ValidationError):
        raise _error(422, _REQUEST_ERROR) from None


def _request_body_schema(schema: dict[str, object]) -> dict[str, object]:
    return {"requestBody": {"required": True, "content": {"application/json": {"schema": schema}}}}


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


def ensure_gbm_microenvironment_graph_ready() -> MicroenvironmentGraphProfile:
    return microenvironment_graph_profile()


@router.get("/profile", response_model=MicroenvironmentGraphProfile)
def profile(response: Response) -> MicroenvironmentGraphProfile:
    result = microenvironment_graph_profile()
    _headers(response, profile_digest=result.profile_digest)
    return result


@router.get("/demo", response_model=MicroenvironmentGraphRequest)
def demo(response: Response) -> MicroenvironmentGraphRequest:
    result = synthetic_microenvironment_graph_request()
    _headers(
        response,
        profile_digest=microenvironment_graph_profile().profile_digest,
        request_digest=result.request_digest,
    )
    return result


@router.post(
    "/analyze",
    response_model=MicroenvironmentGraphResult,
    openapi_extra=_request_body_schema(_REQUEST_ADAPTER.json_schema()),
)
async def analyze(request: Request, response: Response) -> MicroenvironmentGraphResult:
    typed = await _typed_body(request, _REQUEST_ADAPTER, MICROENVIRONMENT_GRAPH_REQUEST_MAX_BYTES)
    try:
        result = analyze_microenvironment_graph(typed)
    except (RuntimeError, TypeError, ValueError, ValidationError):
        raise _error(422, _RESULT_ERROR) from None
    if len(canonical_json_bytes(result)) > MICROENVIRONMENT_GRAPH_RESULT_MAX_BYTES:
        raise _error(500, "GBM microenvironment graph result exceeded the byte limit")
    _headers(
        response,
        profile_digest=result.profile_digest,
        request_digest=result.request_digest,
        result_digest=result.result_digest,
    )
    return result


@router.post(
    "/verify",
    response_model=MicroenvironmentGraphReplayResult,
    openapi_extra=_request_body_schema(_REPLAY_ADAPTER.json_schema()),
)
async def verify(request: Request, response: Response) -> MicroenvironmentGraphReplayResult:
    envelope = await _typed_body(request, _REPLAY_ADAPTER, MICROENVIRONMENT_GRAPH_REPLAY_MAX_BYTES)
    try:
        result = verify_microenvironment_graph_replay(envelope)
    except (RuntimeError, TypeError, ValueError, ValidationError):
        raise _error(422, _REPLAY_ERROR) from None
    if not result.verified:
        raise _error(422, _REPLAY_ERROR)
    _headers(
        response,
        profile_digest=microenvironment_graph_profile().profile_digest,
        request_digest=result.recomputed_request_digest,
        result_digest=result.recomputed_result_digest,
    )
    return result


def _read_typed[T](path: Path, adapter: TypeAdapter[T], maximum: int) -> T:
    try:
        body = read_bounded(path, maximum)
        strict_json_loads(body, max_bytes=maximum)
        return adapter.validate_json(body, strict=True)
    except (OSError, RequestBodyTooLargeError, StrictJsonError, ValidationError):
        raise typer.BadParameter(_REQUEST_ERROR) from None


def _emit(value: object) -> None:
    typer.echo(canonical_json_bytes(value).decode())


@cli.command("profile")
def cli_profile() -> None:
    _emit(microenvironment_graph_profile())


@cli.command("demo")
def cli_demo() -> None:
    _emit(synthetic_microenvironment_graph_request())


@cli.command("analyze")
def cli_analyze(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    typed = _read_typed(request, _REQUEST_ADAPTER, MICROENVIRONMENT_GRAPH_REQUEST_MAX_BYTES)
    try:
        result = analyze_microenvironment_graph(typed)
    except (RuntimeError, TypeError, ValueError, ValidationError) as error:
        raise typer.BadParameter(_RESULT_ERROR) from error
    if output is None:
        _emit(result)
    else:
        if output.exists():
            raise typer.BadParameter(_OUTPUT_EXISTS_ERROR)
        output.write_bytes(canonical_json_bytes(result) + b"\n")


@cli.command("verify")
def cli_verify(
    envelope: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    typed = _read_typed(envelope, _REPLAY_ADAPTER, MICROENVIRONMENT_GRAPH_REPLAY_MAX_BYTES)
    try:
        result = verify_microenvironment_graph_replay(typed)
    except (RuntimeError, TypeError, ValueError, ValidationError) as error:
        raise typer.BadParameter(_REPLAY_ERROR) from error
    _emit(result)
    if not result.verified:
        raise typer.Exit(code=1)


__all__ = [
    "MICROENVIRONMENT_GRAPH_REPLAY_MAX_BYTES",
    "MICROENVIRONMENT_GRAPH_REQUEST_MAX_BYTES",
    "MICROENVIRONMENT_GRAPH_RESULT_MAX_BYTES",
    "MICROENVIRONMENT_GRAPH_ROUTE_PREFIX",
    "cli",
    "demo",
    "ensure_gbm_microenvironment_graph_ready",
    "profile",
    "router",
    "verify",
]

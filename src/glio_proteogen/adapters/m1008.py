"""Strict FastAPI and Typer adapters for provisional M10-08."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Literal

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from glio_proteogen.adapters.limits import (
    RequestBodyTooLargeError,
    RequestSizeLimitMiddleware,
    read_bounded,
)
from glio_proteogen.contracts.m10_08 import (
    M1008_MAX_CANONICAL_REQUEST_BYTES,
    M1008_MAX_CANONICAL_RESULT_BYTES,
    ProteinRnaEvidencePublicationResult,
    PublishProteinRnaEvidenceRequest,
    contract_json_schema,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c10_pathway_proteotype_factors import (
    m10_08_evidence_explanation_publisher as m1008_runtime,
)

ContractName = Literal[
    "request",
    "output",
    "evidence-bundle",
    "explanation",
    "source",
    "assumption",
    "counter-evidence",
    "diagnostic",
    "reconstruction-step",
]


def create_m1008_app(
    service: m1008_runtime.M1008EvidencePublisherService | None = None,
) -> FastAPI:
    """Create an isolated API with strict duplicate-safe JSON boundaries."""

    active_service = service or m1008_runtime.M1008EvidencePublisherService()
    app = FastAPI(title="GLIO-PROTEOGEN M10-08", version="0.1.0-provisional")
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=M1008_MAX_CANONICAL_REQUEST_BYTES,
        result_max_bytes=M1008_MAX_CANONICAL_RESULT_BYTES,
    )

    @app.get("/v1/m10-08/schema/{contract}")
    async def export_schema(contract: ContractName) -> dict[str, object]:
        return contract_json_schema(contract)

    @app.post("/v1/m10-08/validate")
    async def validate(request: Request) -> JSONResponse:
        typed = await _parse_request(request)
        return JSONResponse({"valid": True, "request": typed.model_dump(mode="json")})

    @app.post("/v1/m10-08/publish")
    async def publish(request: Request) -> JSONResponse:
        typed = await _parse_request(request)
        result = active_service.execute(typed)
        return JSONResponse(result.model_dump(mode="json"))

    @app.post("/v1/m10-08/verify")
    async def verify(request: Request) -> JSONResponse:
        typed = await _parse_result(request)
        if not active_service.verify(typed):
            raise HTTPException(status_code=409, detail="result replay verification failed")
        return JSONResponse({"verified": True, "result_digest": typed.result_digest})

    return app


async def _parse_request(request: Request) -> PublishProteinRnaEvidenceRequest:
    decoded, serialized = await _strict_body(request, max_bytes=M1008_MAX_CANONICAL_REQUEST_BYTES)
    try:
        m1008_runtime.preflight_m1008_authorization(decoded)
    except m1008_runtime.M1008AuthorizationError as error:
        raise HTTPException(status_code=403, detail="M10-08 authorization failed") from error
    try:
        return PublishProteinRnaEvidenceRequest.model_validate_json(serialized, strict=True)
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail={"errors": sanitized_validation_errors(error)},
        ) from error


async def _parse_result(request: Request) -> ProteinRnaEvidencePublicationResult:
    decoded, serialized = await _strict_body(request, max_bytes=M1008_MAX_CANONICAL_RESULT_BYTES)
    try:
        return ProteinRnaEvidencePublicationResult.model_validate_json(serialized, strict=True)
    except ValidationError as error:
        if (
            isinstance(decoded, dict)
            and isinstance(decoded.get("result_digest"), str)
            and decoded["result_digest"] != result_payload_digest(decoded)
        ):
            raise HTTPException(
                status_code=409, detail="result replay verification failed"
            ) from error
        raise HTTPException(
            status_code=422,
            detail={"errors": sanitized_validation_errors(error)},
        ) from error


async def _strict_body(request: Request, *, max_bytes: int) -> tuple[object, bytes]:
    body = await request.body()
    try:
        return strict_json_loads(body, max_bytes=max_bytes), body
    except StrictJsonError as error:
        raise HTTPException(
            status_code=400,
            detail=strict_json_error_detail(error),
        ) from error


m1008_app = typer.Typer(
    name="m10-08",
    help="Publish provisional M10-08 evidence and explanation objects.",
    no_args_is_help=True,
)


@m1008_app.command("export-schema")
def export_schema_cli(
    contract: Annotated[ContractName, typer.Argument(help="Contract schema to export.")],
) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))


@m1008_app.command("validate")
def validate_cli(path: Annotated[str, typer.Argument(help="JSON path, or - for stdin.")]) -> None:
    """Validate one request without publishing it."""

    try:
        typed = _load_request_path(path)
    except (
        m1008_runtime.M1008AuthorizationError,
        StrictJsonError,
        ValidationError,
        OSError,
    ) as error:
        _cli_error(error)
    typer.echo(
        canonical_json_bytes({"valid": True, "request": typed.model_dump(mode="json")}).decode()
    )


@m1008_app.command("publish")
def publish_cli(path: Annotated[str, typer.Argument(help="JSON path, or - for stdin.")]) -> None:
    """Publish one closed evidence bundle or an explicit abstention."""

    try:
        typed = _load_request_path(path)
        result = m1008_runtime.M1008EvidencePublisherService().execute(typed)
    except (
        m1008_runtime.M1008AuthorizationError,
        StrictJsonError,
        ValidationError,
        OSError,
        ValueError,
    ) as error:
        _cli_error(error)
    typer.echo(canonical_json_bytes(result.model_dump(mode="json")).decode())


@m1008_app.command("verify")
def verify_cli(
    path: Annotated[str, typer.Argument(help="Result JSON path, or - for stdin.")],
) -> None:
    """Verify one result's canonical replay digest."""

    try:
        result = _load_result_path(path)
    except (StrictJsonError, ValidationError, OSError, _ResultReplayError) as error:
        if isinstance(error, _ResultReplayError):
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1) from error
        _cli_error(error)
    if not m1008_runtime.M1008EvidencePublisherService.verify(result):
        typer.echo("result replay verification failed", err=True)
        raise typer.Exit(code=1)
    typer.echo(
        canonical_json_bytes({"verified": True, "result_digest": result.result_digest}).decode()
    )


def _load_request_path(path: str) -> PublishProteinRnaEvidenceRequest:
    serialized = _read_path(path, max_bytes=M1008_MAX_CANONICAL_REQUEST_BYTES)
    decoded = strict_json_loads(serialized, max_bytes=M1008_MAX_CANONICAL_REQUEST_BYTES)
    m1008_runtime.preflight_m1008_authorization(decoded)
    return PublishProteinRnaEvidenceRequest.model_validate_json(serialized, strict=True)


def _load_result_path(path: str) -> ProteinRnaEvidencePublicationResult:
    serialized = _read_path(path, max_bytes=M1008_MAX_CANONICAL_RESULT_BYTES)
    decoded = strict_json_loads(serialized, max_bytes=M1008_MAX_CANONICAL_RESULT_BYTES)
    try:
        return ProteinRnaEvidencePublicationResult.model_validate_json(serialized, strict=True)
    except ValidationError as error:
        if (
            isinstance(decoded, dict)
            and isinstance(decoded.get("result_digest"), str)
            and decoded["result_digest"] != result_payload_digest(decoded)
        ):
            raise _ResultReplayError from error
        raise


class _ResultReplayError(ValueError):
    def __init__(self) -> None:
        super().__init__("result replay verification failed")


def _read_path(path: str, *, max_bytes: int) -> bytes:
    if path != "-":
        return read_bounded(Path(path), max_bytes=max_bytes)
    serialized = sys.stdin.buffer.read(max_bytes + 1)
    if len(serialized) > max_bytes:
        raise RequestBodyTooLargeError
    return serialized


def _cli_error(error: Exception) -> None:
    if isinstance(error, StrictJsonError):
        detail = strict_json_error_detail(error)
    elif isinstance(error, m1008_runtime.M1008AuthorizationError):
        detail = {"type": "authorization_failed", "msg": "M10-08 authorization failed"}
    elif isinstance(error, ValidationError):
        detail = {"errors": sanitized_validation_errors(error)}
    else:
        detail = {"type": "request_rejected", "msg": "request could not be processed"}
    typer.echo(json.dumps(detail, sort_keys=True), err=True)
    raise typer.Exit(code=2)


__all__ = ["create_m1008_app", "m1008_app"]

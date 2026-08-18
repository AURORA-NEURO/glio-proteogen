"""Strict FastAPI and Typer adapters for provisional M11-08."""

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
from glio_proteogen.contracts.m11_08 import (
    M1108_MAX_CANONICAL_REQUEST_BYTES,
    M1108_MAX_CANONICAL_RESULT_BYTES,
    AssembleVariantPeptideMechanismDossierRequest,
    VariantPeptideMechanismDossierResult,
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
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_08_mechanism_evidence_dossier as m1108_runtime,
)

ContractName = Literal[
    "request",
    "output",
    "dossier",
    "link",
    "counter-evidence",
    "validation-route",
    "claim-ceiling",
    "configuration",
    "diagnostic",
]


def create_m1108_app(
    service: m1108_runtime.M1108MechanismEvidenceDossierService | None = None,
) -> FastAPI:
    """Create an isolated API with strict duplicate-safe JSON boundaries."""

    active_service = service or m1108_runtime.M1108MechanismEvidenceDossierService()
    app = FastAPI(title="GLIO-PROTEOGEN M11-08", version="0.1.0-provisional")
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=M1108_MAX_CANONICAL_RESULT_BYTES,
    )

    @app.get("/v1/m11-08/schema/{contract}")
    async def export_schema(contract: ContractName) -> dict[str, object]:
        return contract_json_schema(contract)

    @app.post("/v1/m11-08/validate")
    async def validate(request: Request) -> JSONResponse:
        typed = await _parse_request(request)
        return JSONResponse({"valid": True, "request": typed.model_dump(mode="json")})

    @app.post("/v1/m11-08/assemble")
    @app.post("/v1/modules/M11-08/assemble")
    async def assemble(request: Request) -> JSONResponse:
        typed = await _parse_request(request)
        result = active_service.execute(typed)
        return JSONResponse(result.model_dump(mode="json"))

    @app.post("/v1/m11-08/verify")
    @app.post("/v1/modules/M11-08/verify")
    async def verify(request: Request) -> JSONResponse:
        typed = await _parse_result(request)
        if not active_service.verify(typed):
            raise HTTPException(status_code=409, detail="result replay verification failed")
        return JSONResponse({"verified": True, "result_digest": typed.result_digest})

    return app


async def _parse_request(request: Request) -> AssembleVariantPeptideMechanismDossierRequest:
    decoded, serialized = await _strict_body(request, M1108_MAX_CANONICAL_REQUEST_BYTES)
    try:
        m1108_runtime.preflight_m1108_authorization(decoded)
    except m1108_runtime.M1108AuthorizationError as error:
        raise HTTPException(status_code=403, detail="M11-08 authorization failed") from error
    try:
        return AssembleVariantPeptideMechanismDossierRequest.model_validate_json(
            serialized, strict=True
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail={"errors": sanitized_validation_errors(error)},
        ) from error


async def _parse_result(request: Request) -> VariantPeptideMechanismDossierResult:
    decoded, serialized = await _strict_body(request, M1108_MAX_CANONICAL_RESULT_BYTES)
    try:
        return VariantPeptideMechanismDossierResult.model_validate_json(serialized, strict=True)
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


async def _strict_body(request: Request, max_bytes: int) -> tuple[object, bytes]:
    body = await request.body()
    try:
        return strict_json_loads(body, max_bytes=max_bytes), body
    except StrictJsonError as error:
        raise HTTPException(
            status_code=400,
            detail=strict_json_error_detail(error),
        ) from error


m1108_app = typer.Typer(
    name="m11-08",
    help="Assemble a provisional M11-08 mechanism evidence dossier.",
    no_args_is_help=True,
)


@m1108_app.command("export-schema")
def export_schema_cli(
    contract: Annotated[ContractName, typer.Argument(help="Contract schema to export.")],
) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))


@m1108_app.command("validate")
def validate_cli(path: Annotated[str, typer.Argument(help="JSON path, or - for stdin.")]) -> None:
    """Validate one request without assembling a dossier."""

    try:
        typed = _load_request_path(path)
    except (
        m1108_runtime.M1108AuthorizationError,
        StrictJsonError,
        ValidationError,
        OSError,
        ValueError,
        TypeError,
    ) as error:
        _cli_error(error)
    typer.echo(
        canonical_json_bytes({"valid": True, "request": typed.model_dump(mode="json")}).decode()
    )


@m1108_app.command("assemble")
def assemble_cli(path: Annotated[str, typer.Argument(help="JSON path, or - for stdin.")]) -> None:
    """Assemble a review-ready dossier or an explicit safe abstention."""

    try:
        typed = _load_request_path(path)
        result = m1108_runtime.M1108MechanismEvidenceDossierService().execute(typed)
    except (
        m1108_runtime.M1108AuthorizationError,
        StrictJsonError,
        ValidationError,
        OSError,
        ValueError,
        TypeError,
    ) as error:
        _cli_error(error)
    typer.echo(canonical_json_bytes(result.model_dump(mode="json")).decode())


@m1108_app.command("verify")
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
    if not m1108_runtime.M1108MechanismEvidenceDossierService.verify(result):
        typer.echo("result replay verification failed", err=True)
        raise typer.Exit(code=1)
    typer.echo(
        canonical_json_bytes({"verified": True, "result_digest": result.result_digest}).decode()
    )


def _load_request_path(path: str) -> AssembleVariantPeptideMechanismDossierRequest:
    serialized = _read_path(path, M1108_MAX_CANONICAL_REQUEST_BYTES)
    decoded = strict_json_loads(serialized, max_bytes=M1108_MAX_CANONICAL_REQUEST_BYTES)
    m1108_runtime.preflight_m1108_authorization(decoded)
    return AssembleVariantPeptideMechanismDossierRequest.model_validate_json(
        serialized, strict=True
    )


def _load_result_path(path: str) -> VariantPeptideMechanismDossierResult:
    serialized = _read_path(path, M1108_MAX_CANONICAL_RESULT_BYTES)
    decoded = strict_json_loads(serialized, max_bytes=M1108_MAX_CANONICAL_RESULT_BYTES)
    try:
        return VariantPeptideMechanismDossierResult.model_validate_json(serialized, strict=True)
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


def _read_path(path: str, max_bytes: int) -> bytes:
    if path == "-":
        payload = sys.stdin.buffer.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise RequestBodyTooLargeError
        return payload
    return read_bounded(Path(path), max_bytes)


def _cli_error(error: Exception) -> None:
    if isinstance(error, StrictJsonError):
        detail = strict_json_error_detail(error)
    elif isinstance(error, m1108_runtime.M1108AuthorizationError):
        detail = {"type": "authorization_failed", "msg": "M11-08 authorization failed"}
    elif isinstance(error, ValidationError):
        detail = {"errors": sanitized_validation_errors(error)}
    else:
        detail = {"type": "request_rejected", "msg": "request could not be processed"}
    typer.echo(json.dumps(detail, sort_keys=True), err=True)
    raise typer.Exit(code=2)


__all__ = ["create_m1108_app", "m1108_app"]

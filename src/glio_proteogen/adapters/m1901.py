"""Strict FastAPI and Typer adapters for provisional M19-01."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves this runtime type.
from typing import Annotated, Final, cast

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import (
    RequestBodyTooLargeError,
    RequestSizeLimitMiddleware,
    read_bounded,
)
from glio_proteogen.contracts.m19_01 import (
    M1901_MAX_CANONICAL_REQUEST_BYTES,
    M1901_MAX_CANONICAL_RESULT_BYTES,
    ProteotypeUpstreamResolutionResult,
    ResolveProteotypeUpstreamContractsRequest,
)
from glio_proteogen.contracts.m19_01.schema import ContractName, contract_json_schema
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_01_upstream_contract_resolver as m1901,
)

_REQUEST_ADAPTER = TypeAdapter(ResolveProteotypeUpstreamContractsRequest)
_RESULT_ADAPTER = TypeAdapter(ProteotypeUpstreamResolutionResult)
_SERVICE = m1901.M1901Service()
_OUTPUT_EXISTS: Final = "output already exists"

app = FastAPI(
    title="GLIO-PROTEOGEN M19-01 upstream contract resolver",
    version="0.1.0-provisional",
)
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=M1901_MAX_CANONICAL_REQUEST_BYTES,
    result_max_bytes=M1901_MAX_CANONICAL_RESULT_BYTES,
)
m1901_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _json_error(status_code: int, detail: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


async def _validated_body(request: Request) -> ResolveProteotypeUpstreamContractsRequest:
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != (
        "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        decoded = strict_json_loads(body, max_bytes=M1901_MAX_CANONICAL_REQUEST_BYTES)
        m1901.preflight_m1901_authorization(decoded)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    except StrictJsonError as error:
        raise _json_error(422, "invalid JSON request") from error
    except ValidationError as error:
        raise _json_error(
            422, sanitized_validation_errors(error, location_prefix=("body",))
        ) from error
    except m1901.M1901AuthorizationError as error:
        raise _json_error(403, str(error)) from error


@app.get("/v1/m19-01/schema/{name}")
def schema(name: str) -> JSONResponse:
    try:
        document = contract_json_schema(cast("ContractName", name))
    except (KeyError, ValueError) as error:
        raise _json_error(404, "unknown M19-01 contract schema") from error
    return JSONResponse(document)


@app.post("/v1/modules/M19-01/resolve")
async def resolve(request: Request) -> JSONResponse:
    validated = await _validated_body(request)
    try:
        result = _SERVICE.resolve(validated)
    except (ValueError, ValidationError) as error:
        raise _json_error(422, "M19-01 resolution failed") from error
    return JSONResponse(result.model_dump(mode="json"))


@app.post("/v1/modules/M19-01/verify")
async def verify(request: Request) -> JSONResponse:
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != (
        "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        strict_json_loads(body, max_bytes=M1901_MAX_CANONICAL_RESULT_BYTES)
        result = _RESULT_ADAPTER.validate_json(body, strict=True)
        verified = _SERVICE.replay(result)
    except (StrictJsonError, ValidationError, m1901.M1901ReplayError) as error:
        raise _json_error(422, "M19-01 result verification failed") from error
    return JSONResponse(verified.model_dump(mode="json"))


def _load_request(path: Path) -> ResolveProteotypeUpstreamContractsRequest:
    try:
        raw = read_bounded(path, M1901_MAX_CANONICAL_REQUEST_BYTES)
        decoded = strict_json_loads(raw, max_bytes=M1901_MAX_CANONICAL_REQUEST_BYTES)
        m1901.preflight_m1901_authorization(decoded)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    except (
        OSError,
        RequestBodyTooLargeError,
        StrictJsonError,
        ValidationError,
        m1901.M1901AuthorizationError,
    ) as error:
        raise typer.BadParameter("invalid M19-01 request") from error  # noqa: TRY003


def _read_result(path: Path) -> bytes:
    return read_bounded(path, M1901_MAX_CANONICAL_RESULT_BYTES)


@m1901_app.command("export-schema")
def export_schema(name: Annotated[str, typer.Argument(help="M19-01 schema name.")]) -> None:
    try:
        typer.echo(
            json.dumps(contract_json_schema(cast("ContractName", name)), indent=2, sort_keys=True)
        )
    except (KeyError, ValueError) as error:
        typer.echo("unknown M19-01 schema", err=True)
        raise typer.Exit(code=2) from error


@m1901_app.command("resolve")
def resolve_command(
    request_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    if output is not None and output.exists():
        raise typer.BadParameter(_OUTPUT_EXISTS)
    try:
        request = _load_request(request_path)
        result = _SERVICE.resolve(request)
        payload = canonical_json_bytes(result).decode("utf-8")
        if output is None:
            typer.echo(payload)
        else:
            output.write_text(payload + "\n", encoding="utf-8", newline="\n")
    except (OSError, ValueError, typer.BadParameter) as error:
        typer.echo("resolution failed: M19-01 request is invalid", err=True)
        raise typer.Exit(code=1) from error


@m1901_app.command("verify")
def verify_command(
    result_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    try:
        raw = _read_result(result_path)
        strict_json_loads(raw, max_bytes=M1901_MAX_CANONICAL_RESULT_BYTES)
        result = _RESULT_ADAPTER.validate_json(raw, strict=True)
        verified = _SERVICE.replay(result)
    except (
        OSError,
        RequestBodyTooLargeError,
        StrictJsonError,
        ValidationError,
        m1901.M1901ReplayError,
    ) as error:
        typer.echo("verification failed: M19-01 result is invalid", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(canonical_json_bytes(verified).decode("utf-8"))


__all__ = ["app", "m1901_app"]

"""FastAPI and Typer adapters for provisional M17-07."""

# Adapter entry points intentionally keep framework errors sanitized.

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from glio_proteogen.contracts.m17_07 import (
    M1707_MAX_CANONICAL_REQUEST_BYTES,
    ContractName,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c17_metabolomic_lipidomic.m17_07_downstream_typed_export import (
    M1707AuthorizationError,
    M1707ReplayVerificationError,
    M1707Service,
)


def _sanitized(error: Exception) -> str:
    return f"M17-07 request rejected: {type(error).__name__}"


def _parse_bytes(payload: bytes) -> object:
    parsed = strict_json_loads(payload, max_bytes=M1707_MAX_CANONICAL_REQUEST_BYTES)
    return json.loads(canonical_json_bytes(parsed))


def create_app(service: M1707Service | None = None) -> FastAPI:
    """Create a small isolated API for the M17-07 contract."""

    operation = service or M1707Service()
    api = FastAPI(title="GLIO-PROTEOGEN M17-07", version="0.1.0-provisional")

    @api.get("/v1/m17-07/schema/{name}")
    async def schema(name: str) -> JSONResponse:
        try:
            return JSONResponse(contract_json_schema(name))  # type: ignore[arg-type]
        except (KeyError, ValueError, TypeError) as error:
            raise HTTPException(status_code=404, detail="unknown M17-07 contract") from error

    @api.post("/v1/modules/M17-07/export")
    async def export(request: Request) -> JSONResponse:
        try:
            result = operation.execute(_parse_bytes(await request.body()))
        except M1707AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M17-07 authorization denied") from error
        except Exception as error:
            raise HTTPException(status_code=422, detail=_sanitized(error)) from error
        return JSONResponse(result.model_dump(mode="json"))

    @api.post("/v1/modules/M17-07/verify")
    async def verify(request: Request) -> JSONResponse:
        try:
            result = operation.verify(_parse_bytes(await request.body()))
        except M1707ReplayVerificationError as error:
            raise HTTPException(
                status_code=422, detail="M17-07 replay verification failed"
            ) from error
        except Exception as error:
            raise HTTPException(status_code=422, detail=_sanitized(error)) from error
        return JSONResponse(result.model_dump(mode="json"))

    return api


app = create_app()
cli = typer.Typer(help="Provisional M17-07 downstream typed export.")


def _load_path(path: str) -> object:
    if path == "-":
        return _parse_bytes(sys.stdin.buffer.read())
    return _parse_bytes(Path(path).read_bytes())


def _emit(result: object, output: str | None) -> None:
    payload = canonical_json_bytes(result)
    if output is None:
        typer.echo(payload.decode("utf-8"))
        return
    target = Path(output)
    if target.exists():
        typer.echo("M17-07 output exists; refusing overwrite", err=True)
        raise typer.Exit(code=2)
    target.write_bytes(payload)


@cli.command("export-schema")
def export_schema(
    name: Annotated[ContractName, typer.Argument(help="M17-07 contract name.")],
) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    typer.echo(json.dumps(contract_json_schema(name), indent=2, sort_keys=True))


@cli.command("export")
def export_command(
    request: Annotated[str, typer.Argument(help="Request JSON path or '-' for stdin.")],
    output: Annotated[str | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one authorized typed downstream contract."""

    try:
        result = M1707Service().execute(_load_path(request))
        _emit(result, output)
    except M1707AuthorizationError as error:
        typer.echo("M17-07 authorization denied", err=True)
        raise typer.Exit(code=2) from error
    except typer.Exit:
        raise
    except Exception as error:
        typer.echo(_sanitized(error), err=True)
        raise typer.Exit(code=1) from error


@cli.command("verify")
def verify_command(
    result: Annotated[str, typer.Argument(help="Result JSON path or '-' for stdin.")],
) -> None:
    """Verify result digest and deterministic replay."""

    try:
        verified = M1707Service().verify(_load_path(result))
    except Exception as error:
        typer.echo(_sanitized(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(canonical_json_bytes(verified).decode("utf-8"))


__all__ = ["app", "cli", "create_app"]

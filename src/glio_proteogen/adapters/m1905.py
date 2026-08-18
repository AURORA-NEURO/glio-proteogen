"""FastAPI and Typer adapters for provisional M19-05."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.contracts.m19_05 import (
    M1905_MAX_CANONICAL_REQUEST_BYTES,
    M1905_MAX_CANONICAL_RESULT_BYTES,
    ContractName,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_05_workflow_presentation_service import (  # noqa: E501
    M1905AuthorizationError,
    M1905ReplayError,
    M1905Service,
)


def _sanitized(error: Exception) -> str:
    return f"M19-05 request rejected: {type(error).__name__}"


def _parse_bytes(payload: bytes, *, max_bytes: int) -> object:
    parsed = strict_json_loads(payload, max_bytes=max_bytes)
    return json.loads(canonical_json_bytes(parsed))


def create_app(service: M1905Service | None = None) -> FastAPI:
    """Create an isolated strict M19-05 API."""

    operation = service or M1905Service()
    api = FastAPI(title="GLIO-PROTEOGEN M19-05", version="0.1.0-provisional")

    @api.get("/v1/m19-05/schema/{name}")
    async def schema(name: str) -> JSONResponse:
        try:
            return JSONResponse(contract_json_schema(name))  # type: ignore[arg-type]
        except (KeyError, ValueError, TypeError) as error:
            raise HTTPException(status_code=404, detail="unknown M19-05 contract") from error

    @api.post("/v1/modules/M19-05/present")
    async def present(request: Request) -> JSONResponse:
        try:
            result = operation.execute(
                _parse_bytes(await request.body(), max_bytes=M1905_MAX_CANONICAL_REQUEST_BYTES)
            )
        except M1905AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M19-05 authorization denied") from error
        except Exception as error:
            raise HTTPException(status_code=422, detail=_sanitized(error)) from error
        return JSONResponse(result.model_dump(mode="json"))

    @api.post("/v1/modules/M19-05/verify")
    async def verify(request: Request) -> JSONResponse:
        try:
            result = operation.verify(
                _parse_bytes(await request.body(), max_bytes=M1905_MAX_CANONICAL_RESULT_BYTES)
            )
        except M1905ReplayError as error:
            raise HTTPException(
                status_code=422,
                detail="M19-05 replay verification failed",
            ) from error
        except Exception as error:
            raise HTTPException(status_code=422, detail=_sanitized(error)) from error
        return JSONResponse(result.model_dump(mode="json"))

    return api


app = create_app()
cli = typer.Typer(help="Provisional M19-05 workflow presentation service.")


def _read_stdin(max_bytes: int) -> bytes:
    payload = sys.stdin.buffer.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise RequestBodyTooLargeError
    return payload


def _load_path(path: str, *, max_bytes: int) -> object:
    if path == "-":
        return _parse_bytes(_read_stdin(max_bytes), max_bytes=max_bytes)
    return _parse_bytes(read_bounded(Path(path), max_bytes), max_bytes=max_bytes)


def _emit(result: object, output: str | None) -> None:
    payload = canonical_json_bytes(result)
    if output is None:
        typer.echo(payload.decode("utf-8"))
        return
    target = Path(output)
    if target.exists():
        typer.echo("M19-05 output exists; refusing overwrite", err=True)
        raise typer.Exit(code=2)
    target.write_bytes(payload)


@cli.command("export-schema")
def export_schema(
    name: Annotated[ContractName, typer.Argument(help="M19-05 contract name.")],
) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    typer.echo(json.dumps(contract_json_schema(name), indent=2, sort_keys=True))


@cli.command("present")
def present_command(
    request: Annotated[str, typer.Argument(help="Request JSON path or '-' for stdin.")],
    output: Annotated[str | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Present one authorized human-review workspace."""

    try:
        result = M1905Service().execute(
            _load_path(request, max_bytes=M1905_MAX_CANONICAL_REQUEST_BYTES)
        )
        _emit(result, output)
    except M1905AuthorizationError as error:
        typer.echo("M19-05 authorization denied", err=True)
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
        verified = M1905Service().verify(
            _load_path(result, max_bytes=M1905_MAX_CANONICAL_RESULT_BYTES)
        )
    except Exception as error:
        typer.echo(_sanitized(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(canonical_json_bytes(verified).decode("utf-8"))


__all__ = ["app", "cli", "create_app"]

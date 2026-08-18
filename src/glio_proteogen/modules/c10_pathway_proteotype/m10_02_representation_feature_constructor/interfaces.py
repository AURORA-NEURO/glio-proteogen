# ruff: noqa: B008, BLE001, TC003, TRY003
"""API and CLI-neutral interface helpers for M10-02.

Both adapters use the same plugin boundary.  This keeps strict parsing,
authorization, replay sealing, and sanitized errors identical across HTTP and
command-line execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m10_02 import (
    M1002_MAX_CANONICAL_REQUEST_BYTES,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
)

from .engine import RepresentationAuthorizationError
from .plugin import M1002Plugin
from .service import M1002Service

M1002_SCHEMA_NAMES: Final[tuple[str, ...]] = tuple(contract_json_schemas())


def export_schema(name: str) -> dict[str, object]:
    """Return one allow-listed schema without permitting arbitrary traversal."""

    if name not in M1002_SCHEMA_NAMES:
        raise KeyError(name)
    return contract_json_schema(name)  # type: ignore[arg-type]


def _error_response(error: Exception) -> JSONResponse:
    if isinstance(error, StrictJsonError):
        return JSONResponse(status_code=400, content={"errors": [strict_json_error_detail(error)]})
    if isinstance(error, ValidationError):
        return JSONResponse(
            status_code=422,
            content={"errors": sanitized_validation_errors(error)},
        )
    if isinstance(error, RepresentationAuthorizationError):
        return JSONResponse(status_code=403, content={"errors": [{"type": "forbidden"}]})
    return JSONResponse(status_code=400, content={"errors": [{"type": "invalid_request"}]})


def create_m1002_app() -> FastAPI:
    """Create an isolated FastAPI app for the provisional M10-02 surface."""

    app = FastAPI(title="GLIO-PROTEOGEN M10-02", version="0.1.0-provisional")
    plugin = M1002Plugin(M1002Service())

    @app.get("/v1/m10-02/schema/{name}")
    def schema(name: str) -> dict[str, object]:
        try:
            return export_schema(name)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="unknown M10-02 schema") from error

    @app.post("/v1/m10-02/validate")
    async def validate(request: Request) -> JSONResponse:
        try:
            body = await request.body()
            token = plugin.validate(body)
            return JSONResponse(content=token.request.model_dump(mode="json"))
        except Exception as error:  # adapter sanitizes all failures.
            return _error_response(error)

    @app.post("/v1/m10-02/construct")
    async def construct(request: Request) -> JSONResponse:
        try:
            body = await request.body()
            token = plugin.validate(body)
            result = plugin.run(token)
            return JSONResponse(content=result.model_dump(mode="json"))
        except Exception as error:  # adapter sanitizes all failures.
            return _error_response(error)

    return app


app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


@app.command("export-schema")
def export_schema_command(
    name: str = typer.Argument(..., help="M10-02 contract name."),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Write one strict M10-02 schema, refusing overwrite."""

    try:
        document = export_schema(name)
    except KeyError as error:
        raise typer.BadParameter("unknown M10-02 contract name") from error
    rendered = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output is None:
        typer.echo(rendered, nl=False)
        return
    if output.exists():
        raise typer.BadParameter("output already exists; refusing overwrite")
    output.write_text(rendered, encoding="utf-8", newline="\n")


@app.command("validate")
def validate_command(request: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Validate one request without executing the constructor."""

    try:
        token = M1002Plugin(M1002Service()).validate(
            read_bounded(request, M1002_MAX_CANONICAL_REQUEST_BYTES)
        )
    except Exception as error:
        typer.echo(json.dumps(bytes(_error_response(error).body).decode("utf-8"), sort_keys=True))
        raise typer.Exit(code=2) from error
    typer.echo(json.dumps(token.request.model_dump(mode="json"), sort_keys=True))


@app.command("construct")
def construct_command(
    request: Path = typer.Argument(..., exists=True, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Construct one result, refusing to overwrite an existing output."""

    if output is not None and output.exists():
        raise typer.BadParameter("output already exists; refusing overwrite")
    try:
        plugin = M1002Plugin(M1002Service())
        token = plugin.validate(read_bounded(request, M1002_MAX_CANONICAL_REQUEST_BYTES))
        result = plugin.run(token)
    except Exception as error:
        typer.echo(json.dumps(bytes(_error_response(error).body).decode("utf-8"), sort_keys=True))
        raise typer.Exit(code=2) from error
    rendered = json.dumps(result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
    if output is None:
        typer.echo(rendered, nl=False)
    else:
        output.write_text(rendered, encoding="utf-8", newline="\n")


__all__ = ["M1002_SCHEMA_NAMES", "app", "create_m1002_app", "export_schema"]

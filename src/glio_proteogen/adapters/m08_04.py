"""Standalone provisional API and CLI adapters for M08-04.

The repository's historical root adapters predate the M08 module family.  This
module keeps the still-provisional M08-04 surface isolated while preserving one
strict parse-once path for FastAPI, Typer, and the plugin boundary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m08_04 import (
    M0804_MAX_CANONICAL_REQUEST_BYTES,
    ContractName,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import sanitized_validation_errors, strict_json_loads
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_04_probabilistic_estimator as m0804_runtime,
)

_PATH_HELP = "Path to a canonical M08-04 JSON request; use '-' for stdin."


def _json_error(error: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "invalid M08-04 request", "issues": sanitized_validation_errors(error)},
    )


def create_m0804_app(service: m0804_runtime.M0804Service | None = None) -> FastAPI:
    """Create a minimal FastAPI app with strict parse-once request handling."""

    executor = service or m0804_runtime.M0804Service()
    app = FastAPI(title="GLIO-PROTEOGEN M08-04 (provisional)", version="0.1.0-provisional")

    @app.get("/v1/contracts/M08-04/{name}/schema", tags=["contracts"])
    def export_contract_schema(name: ContractName) -> dict[str, object]:
        return contract_json_schema(name)

    @app.post("/v1/modules/M08-04/probabilistic-estimate", tags=["M08-04"])
    async def estimate(request: Request) -> JSONResponse:
        raw = await request.body()
        if len(raw) > M0804_MAX_CANONICAL_REQUEST_BYTES:
            return JSONResponse(status_code=413, content={"detail": "request too large"})
        try:
            candidate = strict_json_loads(raw, max_bytes=M0804_MAX_CANONICAL_REQUEST_BYTES)
            typed = m0804_runtime.validate_json_request(candidate, raw)
            result = executor.execute(typed)
        except m0804_runtime.M0804AuthorizationError as error:
            return JSONResponse(status_code=403, content={"detail": str(error)})
        except ValidationError as error:
            return _json_error(error)
        except ValueError as error:
            return JSONResponse(status_code=422, content={"detail": str(error)})
        return JSONResponse(result.model_dump(mode="json"))

    return app


app = create_m0804_app()
m0804_app = typer.Typer(no_args_is_help=True, help="M08-04 probabilistic estimator (provisional).")


def _read_request(path: str) -> tuple[object, bytes]:
    if path == "-":
        raw = sys.stdin.buffer.read(M0804_MAX_CANONICAL_REQUEST_BYTES + 1)
    else:
        raw = read_bounded(Path(path), M0804_MAX_CANONICAL_REQUEST_BYTES)
    return strict_json_loads(raw, max_bytes=M0804_MAX_CANONICAL_REQUEST_BYTES), raw


@m0804_app.command("export-schema")
def export_schema(
    name: Annotated[ContractName, typer.Argument(help="Contract name to export.")],
) -> None:
    """Print one strict provisional JSON Schema to stdout."""

    typer.echo(json.dumps(contract_json_schema(name), indent=2, sort_keys=True))


@m0804_app.command("validate")
def validate(
    request: Annotated[str, typer.Argument(help=_PATH_HELP)],
) -> None:
    """Parse and validate one request without executing the estimator."""

    try:
        candidate, raw = _read_request(request)
        typed = m0804_runtime.validate_json_request(candidate, raw)
    except (OSError, TypeError, ValueError, ValidationError) as error:
        typer.echo(f"M08-04 validation failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(typed.model_dump(mode="json"), indent=2, sort_keys=True))


@m0804_app.command("estimate")
def estimate_command(
    request: Annotated[str, typer.Argument(help=_PATH_HELP)],
) -> None:
    """Execute one request and print the canonical result envelope."""

    try:
        candidate, raw = _read_request(request)
        typed = m0804_runtime.validate_json_request(candidate, raw)
        result = m0804_runtime.M0804Service().execute(typed)
    except m0804_runtime.M0804AuthorizationError as error:
        typer.echo(f"M08-04 estimate forbidden: {error}", err=True)
        raise typer.Exit(code=1) from error
    except (OSError, TypeError, ValueError, ValidationError) as error:
        typer.echo(f"M08-04 estimate failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))


__all__ = ["app", "create_m0804_app", "m0804_app"]

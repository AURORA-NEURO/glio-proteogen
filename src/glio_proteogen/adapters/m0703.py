"""Dedicated API and CLI adapters for the provisional M07-03 boundary.

The repository-wide adapters remain unchanged while the dossier has not frozen
the M07-03 ABI.  This adapter therefore provides an isolated, strict transport
surface that can be removed or renamed without changing the stable API.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated

import typer
from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m07_03 import (
    EstimateCopyNumberDosageBaselineRequest,
    EstimateCopyNumberDosageBaselineResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_03_mature_baseline_estimator import (
    M0703AuthorizationError,
    M0703ReplayVerificationError,
    M0703Service,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_REQUEST_ADAPTER = TypeAdapter(EstimateCopyNumberDosageBaselineRequest)
_RESULT_ADAPTER = TypeAdapter(EstimateCopyNumberDosageBaselineResult)


def _strict_json_bytes(payload: bytes) -> bytes:
    """Reject duplicate/non-finite JSON, retaining JSON scalar representations."""

    parsed = strict_json_loads(payload, max_bytes=4 * 1024 * 1024)
    return canonical_json_bytes(parsed)


def create_m0703_app(
    service_factory: Callable[[], M0703Service] = M0703Service,
) -> FastAPI:
    """Build a strict FastAPI app for provisional baseline operations."""

    app = FastAPI(
        title="GLIO-PROTEOGEN M07-03 (provisional)",
        version="0.1.0-provisional",
        docs_url=None,
        redoc_url=None,
    )
    service = service_factory()

    @app.get("/v1/m07-03/schema/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in contract_json_schemas():
            raise HTTPException(status_code=404, detail="unknown M07-03 schema")
        return contract_json_schema(name)

    @app.post(
        "/v1/m07-03/baseline/estimate",
        response_model=EstimateCopyNumberDosageBaselineResult,
    )
    async def estimate(request: Request) -> object:
        try:
            typed = _REQUEST_ADAPTER.validate_json(
                _strict_json_bytes(await request.body()),
                strict=True,
            )
            return service.execute(typed)
        except M0703AuthorizationError as error:
            raise HTTPException(
                status_code=403,
                detail="authorization controls are unresolved",
            ) from error
        except StrictJsonError as error:
            raise HTTPException(status_code=400, detail="invalid strict JSON request") from error
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail=sanitized_validation_errors(error),
            ) from error

    @app.post(
        "/v1/m07-03/baseline/verify",
        response_model=EstimateCopyNumberDosageBaselineResult,
    )
    async def verify(request: Request) -> object:
        try:
            typed = _RESULT_ADAPTER.validate_json(
                _strict_json_bytes(await request.body()),
                strict=True,
            )
            return service.verify(typed)
        except M0703ReplayVerificationError as error:
            raise HTTPException(
                status_code=409,
                detail="result replay verification failed",
            ) from error
        except (StrictJsonError, ValidationError) as error:
            raise HTTPException(status_code=422, detail="invalid M07-03 result envelope") from error

    return app


m0703_app = typer.Typer(
    name="m07-03",
    help="Provisional M07-03 mature baseline estimator operations.",
    no_args_is_help=True,
)


@m0703_app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="Schema name, or 'all'.")],
) -> None:
    """Export one strict JSON Schema without writing files."""

    if name == "all":
        typer.echo(json.dumps(contract_json_schemas(), indent=2, sort_keys=True))
        return
    if name not in contract_json_schemas():
        typer.echo("unknown M07-03 schema", err=True)
        raise typer.Exit(code=2)
    typer.echo(json.dumps(contract_json_schema(name), indent=2, sort_keys=True))


def _read_request(path: typer.FileText) -> EstimateCopyNumberDosageBaselineRequest:
    parsed = _strict_json_bytes(path.read().encode("utf-8"))
    return _REQUEST_ADAPTER.validate_json(parsed, strict=True)


@m0703_app.command("validate")
def validate_request(
    path: Annotated[typer.FileText, typer.Argument(help="Strict JSON request file.")],
) -> None:
    """Validate one request, preserving the parse-once boundary."""

    try:
        request = _read_request(path)
        typer.echo(canonical_json_bytes(request.model_dump(mode="json")).decode("utf-8"))
    except (StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(json.dumps({"detail": str(error)}), err=True)
        raise typer.Exit(code=2) from error


@m0703_app.command("estimate")
def estimate_request(
    path: Annotated[typer.FileText, typer.Argument(help="Strict JSON request file.")],
) -> None:
    """Execute one request and emit the canonical result envelope."""

    try:
        result = M0703Service().execute(_read_request(path))
        typer.echo(canonical_json_bytes(result.model_dump(mode="json")).decode("utf-8"))
    except M0703AuthorizationError as error:
        typer.echo(json.dumps({"detail": "authorization controls are unresolved"}), err=True)
        raise typer.Exit(code=3) from error
    except (StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(json.dumps({"detail": str(error)}), err=True)
        raise typer.Exit(code=2) from error


__all__ = [
    "create_m0703_app",
    "estimate_request",
    "export_schema",
    "m0703_app",
    "validate_request",
]

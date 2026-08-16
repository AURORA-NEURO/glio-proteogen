"""Dedicated API and CLI adapters for the provisional M06-08 boundary.

The repository-wide adapters intentionally remain stable while M06-08's ABI is
under owner review.  This module gives the provisional lane a complete,
testable transport surface without silently claiming that its endpoint or
operation is part of the frozen public API.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated

import typer
from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m06_08 import (
    ProteinAbundanceEvidencePublicationResult,
    PublishProteinAbundanceEvidenceRequest,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c06_protein_abundance.m06_08_evidence_explanation_publisher import (
    M0608EvidencePublisherAuthorizationError,
    M0608ReplayVerificationError,
    M0608Service,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_REQUEST_ADAPTER = TypeAdapter(PublishProteinAbundanceEvidenceRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinAbundanceEvidencePublicationResult)


def _strict_json_bytes(payload: bytes) -> bytes:
    """Reject duplicate/non-finite JSON, then retain JSON scalar representations."""

    parsed = strict_json_loads(payload, max_bytes=4 * 1024 * 1024)
    return canonical_json_bytes(parsed)


def _validation_detail(error: ValidationError) -> list[dict[str, object]]:
    return sanitized_validation_errors(error)


def create_m0608_app(
    service_factory: Callable[[], M0608Service] = M0608Service,
) -> FastAPI:
    """Build a small FastAPI app with strict validation and sanitized errors."""

    app = FastAPI(
        title="GLIO-PROTEOGEN M06-08 (provisional)",
        version="0.1.0-provisional",
        docs_url=None,
        redoc_url=None,
    )
    service = service_factory()

    @app.get("/v1/m06-08/schema/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in contract_json_schemas():
            raise HTTPException(status_code=404, detail="unknown M06-08 schema")
        return contract_json_schema(name)

    @app.post(
        "/v1/m06-08/evidence/publish",
        response_model=ProteinAbundanceEvidencePublicationResult,
    )
    async def publish(request: Request) -> object:
        try:
            typed = _REQUEST_ADAPTER.validate_json(
                _strict_json_bytes(await request.body()),
                strict=True,
            )
            return service.execute(typed)
        except M0608EvidencePublisherAuthorizationError as error:
            raise HTTPException(
                status_code=403,
                detail="authorization controls are unresolved",
            ) from error
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=_validation_detail(error)) from error
        except StrictJsonError as error:
            raise HTTPException(status_code=400, detail="invalid strict JSON request") from error

    @app.post(
        "/v1/m06-08/evidence/verify",
        response_model=ProteinAbundanceEvidencePublicationResult,
    )
    async def verify(request: Request) -> object:
        try:
            typed = _RESULT_ADAPTER.validate_json(
                _strict_json_bytes(await request.body()),
                strict=True,
            )
            return service.verify(typed)
        except M0608ReplayVerificationError as error:
            raise HTTPException(
                status_code=409,
                detail="result replay verification failed",
            ) from error
        except (StrictJsonError, ValidationError) as error:
            raise HTTPException(status_code=422, detail="invalid M06-08 result envelope") from error

    return app


m0608_app = typer.Typer(
    name="m06-08",
    help="Provisional M06-08 evidence/explanation publisher operations.",
    no_args_is_help=True,
)


@m0608_app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="Schema name, or 'all'.")],
) -> None:
    """Export one strict JSON Schema without writing files."""

    if name == "all":
        typer.echo(json.dumps(contract_json_schemas(), indent=2, sort_keys=True))
        return
    if name not in contract_json_schemas():
        typer.echo("unknown M06-08 schema", err=True)
        raise typer.Exit(code=2)
    typer.echo(
        json.dumps(
            contract_json_schema(name),
            indent=2,
            sort_keys=True,
        )
    )


@m0608_app.command("validate")
def validate_request(
    path: Annotated[typer.FileText, typer.Argument(help="Strict JSON request file.")],
) -> None:
    """Validate one request, preserving the parse-once boundary."""

    try:
        parsed = _strict_json_bytes(path.read().encode("utf-8"))
        request = _REQUEST_ADAPTER.validate_json(parsed, strict=True)
        typer.echo(canonical_json_bytes(request.model_dump(mode="json")).decode("utf-8"))
    except (ValidationError, ValueError) as error:
        typer.echo(json.dumps({"detail": str(error)}), err=True)
        raise typer.Exit(code=2) from error


@m0608_app.command("publish")
def publish_request(
    path: Annotated[typer.FileText, typer.Argument(help="Strict JSON request file.")],
) -> None:
    """Execute one request and emit the canonical result envelope."""

    try:
        parsed = _strict_json_bytes(path.read().encode("utf-8"))
        result = M0608Service().execute(_REQUEST_ADAPTER.validate_json(parsed, strict=True))
        typer.echo(canonical_json_bytes(result.model_dump(mode="json")).decode("utf-8"))
    except M0608EvidencePublisherAuthorizationError as error:
        typer.echo(json.dumps({"detail": "authorization controls are unresolved"}), err=True)
        raise typer.Exit(code=3) from error
    except (ValidationError, ValueError) as error:
        typer.echo(json.dumps({"detail": str(error)}), err=True)
        raise typer.Exit(code=2) from error


__all__ = ["create_m0608_app", "export_schema", "m0608_app", "publish_request", "validate_request"]

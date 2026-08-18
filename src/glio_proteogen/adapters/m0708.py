"""Dedicated FastAPI and Typer adapters for provisional M07-08.

The repository-wide adapters remain stable while the dossier leaves this
module's endpoint and media type unfrozen.  Both adapters use the same
parse-once, strict JSON and canonical model boundary.
"""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves this runtime type.
from typing import TYPE_CHECKING, Annotated

import typer
from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m07_08 import (
    M0708_MAX_CANONICAL_REQUEST_BYTES,
    ProteotypeEvidencePublicationResult,
    PublishProteotypeEvidenceRequest,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_08_evidence_explanation_publisher import (
    M0708EvidencePublisherAuthorizationError,
    M0708ReplayVerificationError,
    M0708Service,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_REQUEST_ADAPTER = TypeAdapter(PublishProteotypeEvidenceRequest)
_RESULT_ADAPTER = TypeAdapter(ProteotypeEvidencePublicationResult)


def _strict_json_bytes(payload: bytes) -> bytes:
    parsed = strict_json_loads(payload, max_bytes=M0708_MAX_CANONICAL_REQUEST_BYTES)
    return canonical_json_bytes(parsed)


def _validation_detail(error: ValidationError) -> list[dict[str, object]]:
    return sanitized_validation_errors(error)


def create_m0708_app(
    service_factory: Callable[[], M0708Service] = M0708Service,
) -> FastAPI:
    """Build the provisional M07-08 API with sanitized failure responses."""

    app = FastAPI(
        title="GLIO-PROTEOGEN M07-08 (provisional)",
        version="0.1.0-provisional",
        docs_url=None,
        redoc_url=None,
    )
    service = service_factory()

    @app.get("/v1/m07-08/schema/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in contract_json_schemas():
            raise HTTPException(status_code=404, detail="unknown M07-08 schema")
        return contract_json_schema(name)

    @app.post(
        "/v1/m07-08/evidence/publish",
        response_model=ProteotypeEvidencePublicationResult,
    )
    async def publish(request: Request) -> object:
        try:
            typed = _REQUEST_ADAPTER.validate_json(
                _strict_json_bytes(await request.body()),
                strict=True,
            )
            return service.execute(typed)
        except M0708EvidencePublisherAuthorizationError as error:
            raise HTTPException(
                status_code=403,
                detail="authorization controls are unresolved",
            ) from error
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=_validation_detail(error)) from error
        except StrictJsonError as error:
            raise HTTPException(status_code=400, detail="invalid strict JSON request") from error

    @app.post(
        "/v1/m07-08/evidence/verify",
        response_model=ProteotypeEvidencePublicationResult,
    )
    async def verify(request: Request) -> object:
        try:
            typed = _RESULT_ADAPTER.validate_json(
                _strict_json_bytes(await request.body()),
                strict=True,
            )
            return service.verify(typed)
        except M0708ReplayVerificationError as error:
            raise HTTPException(
                status_code=409,
                detail="result replay verification failed",
            ) from error
        except (StrictJsonError, ValidationError) as error:
            raise HTTPException(status_code=422, detail="invalid M07-08 result envelope") from error

    return app


m0708_app = typer.Typer(
    name="m07-08",
    help="Provisional M07-08 evidence/explanation publisher operations.",
    no_args_is_help=True,
)


@m0708_app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="Schema name, or 'all'.")],
) -> None:
    """Export one strict JSON Schema without writing files."""

    if name == "all":
        typer.echo(json.dumps(contract_json_schemas(), indent=2, sort_keys=True))
        return
    if name not in contract_json_schemas():
        typer.echo("unknown M07-08 schema", err=True)
        raise typer.Exit(code=2)
    typer.echo(json.dumps(contract_json_schema(name), indent=2, sort_keys=True))


@m0708_app.command("validate")
def validate_request(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True, readable=True, dir_okay=False, help="Strict JSON request file."
        ),
    ],
) -> None:
    """Validate one request while retaining the parse-once boundary."""

    try:
        parsed = _strict_json_bytes(read_bounded(path))
        request = _REQUEST_ADAPTER.validate_json(parsed, strict=True)
        typer.echo(canonical_json_bytes(request.model_dump(mode="json")).decode("utf-8"))
    except (StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(json.dumps({"detail": str(error)}), err=True)
        raise typer.Exit(code=2) from error


@m0708_app.command("publish")
def publish_request(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True, readable=True, dir_okay=False, help="Strict JSON request file."
        ),
    ],
) -> None:
    """Execute one request and emit the canonical result envelope."""

    try:
        parsed = _strict_json_bytes(read_bounded(path))
        result = M0708Service().execute(_REQUEST_ADAPTER.validate_json(parsed, strict=True))
        typer.echo(canonical_json_bytes(result.model_dump(mode="json")).decode("utf-8"))
    except M0708EvidencePublisherAuthorizationError as error:
        typer.echo(json.dumps({"detail": "authorization controls are unresolved"}), err=True)
        raise typer.Exit(code=3) from error
    except (StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(json.dumps({"detail": str(error)}), err=True)
        raise typer.Exit(code=2) from error


__all__ = ["create_m0708_app", "export_schema", "m0708_app", "publish_request", "validate_request"]

"""Dedicated FastAPI/Typer adapters for provisional M07-04.

The repository-wide adapters stay untouched while the dossier leaves the
M07-04 ABI unfrozen.  This isolated surface enforces strict parse-once JSON,
sanitized errors, canonical schema export, and service/plugin parity.
"""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves this runtime type.
from typing import TYPE_CHECKING, Annotated

import typer
from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import (
    MAX_REQUEST_BYTES,
    RequestSizeLimitMiddleware,
    read_bounded,
)
from glio_proteogen.contracts.m07_04 import (
    M0704_MAX_CANONICAL_REQUEST_BYTES,
    EstimateCopyNumberDosageProbabilisticRequest,
    EstimateCopyNumberDosageProbabilisticResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c07_copy_number_dosage.m07_04_probabilistic_advanced_estimator import (
    M0704Service,
    ProbabilisticEstimatorAuthorizationError,
    ProbabilisticEstimatorInputError,
    ProbabilisticEstimatorReplayError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_REQUEST_ADAPTER = TypeAdapter(EstimateCopyNumberDosageProbabilisticRequest)
_RESULT_ADAPTER = TypeAdapter(EstimateCopyNumberDosageProbabilisticResult)


def _strict_json_bytes(payload: bytes) -> bytes:
    parsed = strict_json_loads(payload, max_bytes=M0704_MAX_CANONICAL_REQUEST_BYTES)
    return canonical_json_bytes(parsed)


def create_m0704_app(
    service_factory: Callable[[], M0704Service] = M0704Service,
) -> FastAPI:
    """Build a strict FastAPI app for provisional posterior operations."""

    app = FastAPI(
        title="GLIO-PROTEOGEN M07-04 (provisional)",
        version="0.1.0-provisional",
        docs_url=None,
        redoc_url=None,
    )
    service = service_factory()
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=MAX_REQUEST_BYTES,
        result_max_bytes=MAX_REQUEST_BYTES * 2,
    )

    @app.get("/v1/m07-04/schema/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in contract_json_schemas():
            raise HTTPException(status_code=404, detail="unknown M07-04 schema")
        return contract_json_schema(name)

    @app.post(
        "/v1/m07-04/probabilistic/estimate",
        response_model=EstimateCopyNumberDosageProbabilisticResult,
    )
    async def estimate(request: Request) -> object:
        try:
            typed = _REQUEST_ADAPTER.validate_json(
                _strict_json_bytes(await request.body()), strict=True
            )
            return service.execute(typed)
        except ProbabilisticEstimatorAuthorizationError as error:
            raise HTTPException(
                status_code=403,
                detail="authorization controls are unresolved",
            ) from error
        except (StrictJsonError, ProbabilisticEstimatorInputError) as error:
            raise HTTPException(status_code=400, detail="invalid strict JSON request") from error
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail=sanitized_validation_errors(error),
            ) from error

    @app.post(
        "/v1/m07-04/probabilistic/verify",
        response_model=EstimateCopyNumberDosageProbabilisticResult,
    )
    async def verify(request: Request) -> object:
        try:
            typed = _RESULT_ADAPTER.validate_json(
                _strict_json_bytes(await request.body()), strict=True
            )
            return service.verify(typed)
        except ProbabilisticEstimatorReplayError as error:
            raise HTTPException(
                status_code=409,
                detail="result replay verification failed",
            ) from error
        except (StrictJsonError, ValidationError) as error:
            raise HTTPException(status_code=422, detail="invalid M07-04 result envelope") from error

    return app


m0704_app = typer.Typer(
    name="m07-04",
    help="Provisional M07-04 probabilistic/advanced estimator operations.",
    no_args_is_help=True,
)


@m0704_app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="Schema name, or 'all'.")],
) -> None:
    """Export one strict JSON Schema without writing files."""

    if name == "all":
        typer.echo(json.dumps(contract_json_schemas(), indent=2, sort_keys=True))
        return
    if name not in contract_json_schemas():
        typer.echo("unknown M07-04 schema", err=True)
        raise typer.Exit(code=2)
    typer.echo(json.dumps(contract_json_schema(name), indent=2, sort_keys=True))


def _read_request(path: Path) -> EstimateCopyNumberDosageProbabilisticRequest:
    parsed = _strict_json_bytes(read_bounded(path))
    return _REQUEST_ADAPTER.validate_json(parsed, strict=True)


@m0704_app.command("validate")
def validate_request(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True, readable=True, dir_okay=False, help="Strict JSON request file."
        ),
    ],
) -> None:
    """Validate one request while preserving the parse-once boundary."""

    try:
        request = _read_request(path)
        typer.echo(canonical_json_bytes(request.model_dump(mode="json")).decode("utf-8"))
    except (StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(json.dumps({"detail": str(error)}), err=True)
        raise typer.Exit(code=2) from error


@m0704_app.command("estimate")
def estimate_request(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True, readable=True, dir_okay=False, help="Strict JSON request file."
        ),
    ],
) -> None:
    """Execute one request and emit its canonical result envelope."""

    try:
        result = M0704Service().execute(_read_request(path))
        typer.echo(canonical_json_bytes(result.model_dump(mode="json")).decode("utf-8"))
    except ProbabilisticEstimatorAuthorizationError as error:
        typer.echo(json.dumps({"detail": "authorization controls are unresolved"}), err=True)
        raise typer.Exit(code=3) from error
    except (StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(json.dumps({"detail": str(error)}), err=True)
        raise typer.Exit(code=2) from error


@m0704_app.command("verify")
def verify_request(
    path: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, dir_okay=False, help="Strict JSON result file."),
    ],
) -> None:
    """Verify one result digest and replay its request."""

    try:
        parsed = _RESULT_ADAPTER.validate_json(_strict_json_bytes(read_bounded(path)), strict=True)
        result = M0704Service().verify(parsed)
        typer.echo(canonical_json_bytes(result.model_dump(mode="json")).decode("utf-8"))
    except ProbabilisticEstimatorReplayError as error:
        typer.echo(json.dumps({"detail": "result replay verification failed"}), err=True)
        raise typer.Exit(code=4) from error
    except (StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(json.dumps({"detail": str(error)}), err=True)
        raise typer.Exit(code=2) from error


__all__ = [
    "create_m0704_app",
    "estimate_request",
    "export_schema",
    "m0704_app",
    "validate_request",
    "verify_request",
]

"""Strict FastAPI and Typer adapters for provisional M10-05."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Final, Literal, cast

import typer
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestSizeLimitMiddleware, read_bounded
from glio_proteogen.contracts.m10_05 import (
    M1005_MAX_CANONICAL_REQUEST_BYTES,
    M1005_MAX_CANONICAL_RESULT_BYTES,
    IntegrateProteinRnaConstraintsRequest,
    ProteinRnaConstraintIntegrationResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_05_mechanism_constraint_integrator import (  # noqa: E501
    M1005ConstraintAuthorizationError,
    M1005ReplayVerificationError,
    M1005Service,
)

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateProteinRnaConstraintsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaConstraintIntegrationResult)
_CONTRACT_NAMES: Final = frozenset(
    {"request", "output", "constraint", "constraint-set", "evaluation", "ablation", "estimate"}
)


def _validated_json(payload: bytes, *, result: bool = False) -> object:
    """Parse once, canonicalize, and strictly validate one JSON envelope."""

    limit = M1005_MAX_CANONICAL_RESULT_BYTES if result else M1005_MAX_CANONICAL_REQUEST_BYTES
    parsed = strict_json_loads(payload, max_bytes=limit)
    canonical = canonical_json_bytes(parsed)
    return (_RESULT_ADAPTER if result else _REQUEST_ADAPTER).validate_json(canonical, strict=True)


def _validation_detail(error: ValidationError) -> list[dict[str, object]]:
    return sanitized_validation_errors(error, location_prefix=("body",))


def create_m1005_app(service: M1005Service | None = None) -> FastAPI:  # noqa: C901
    """Create an isolated M10-05 ASGI application."""

    lane = service or M1005Service()
    app = FastAPI(title="GLIO-PROTEOGEN M10-05 (provisional)", version="0.1.0-provisional")
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=M1005_MAX_CANONICAL_REQUEST_BYTES,
        result_max_bytes=M1005_MAX_CANONICAL_RESULT_BYTES,
    )

    @app.get("/v1/m10-05/schema/{contract}")
    async def export_schema(contract: str) -> JSONResponse:
        if contract not in _CONTRACT_NAMES:
            return JSONResponse(status_code=404, content={"detail": "unknown contract"})
        return JSONResponse(content=contract_json_schema(contract))  # type: ignore[arg-type]

    @app.post("/v1/m10-05/validate")
    async def validate(request: Request) -> JSONResponse:
        try:
            parsed = _validated_json(await request.body())
        except StrictJsonError as error:
            return JSONResponse(
                status_code=400, content={"detail": strict_json_error_detail(error)}
            )
        except ValidationError as error:
            return JSONResponse(status_code=422, content={"detail": _validation_detail(error)})
        typed = cast("IntegrateProteinRnaConstraintsRequest", parsed)
        return JSONResponse(content={"valid": True, "request": typed.model_dump(mode="json")})

    @app.post("/v1/m10-05/integrate")
    async def integrate(request: Request) -> JSONResponse:
        try:
            parsed = _validated_json(await request.body())
            typed = cast("IntegrateProteinRnaConstraintsRequest", parsed)
            result = lane._execute_validated(typed)
        except StrictJsonError as error:
            return JSONResponse(
                status_code=400, content={"detail": strict_json_error_detail(error)}
            )
        except ValidationError as error:
            return JSONResponse(status_code=422, content={"detail": _validation_detail(error)})
        except M1005ConstraintAuthorizationError:
            return JSONResponse(
                status_code=403, content={"detail": "caller controls are not accepted"}
            )
        return JSONResponse(content=result.model_dump(mode="json"))

    @app.post("/v1/m10-05/verify")
    async def verify(request: Request) -> JSONResponse:
        try:
            parsed = _validated_json(await request.body(), result=True)
            result = lane.verify(parsed)
        except StrictJsonError as error:
            return JSONResponse(
                status_code=400, content={"detail": strict_json_error_detail(error)}
            )
        except (ValidationError, M1005ReplayVerificationError):
            return JSONResponse(
                status_code=409, content={"detail": "receipt replay verification failed"}
            )
        return JSONResponse(content={"verified": True, "result": result.model_dump(mode="json")})

    return app


RequestPath = Annotated[Path, typer.Argument(exists=True, readable=True, dir_okay=False)]
ContractArgument = Annotated[
    Literal[
        "request", "output", "constraint", "constraint-set", "evaluation", "ablation", "estimate"
    ],
    typer.Argument(help="Provisional M10-05 contract name."),
]
m1005_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _read_request(path: Path, *, result: bool = False) -> object:
    max_bytes = M1005_MAX_CANONICAL_RESULT_BYTES if result else M1005_MAX_CANONICAL_REQUEST_BYTES
    return _validated_json(read_bounded(path, max_bytes=max_bytes), result=result)


def _emit(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


@m1005_app.command("export-schema")
def export_schema_command(contract: ContractArgument) -> None:
    """Export one strict JSON Schema."""

    _emit(contract_json_schema(contract))


@m1005_app.command("validate")
def validate_command(request: RequestPath) -> None:
    """Validate one request without executing the integrator."""

    try:
        parsed = _read_request(request)
    except (OSError, StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(
            "M10-05 validation failed: request does not match the declared contract", err=True
        )
        raise typer.Exit(code=2) from error
    typed = cast("IntegrateProteinRnaConstraintsRequest", parsed)
    _emit({"valid": True, "request": typed.model_dump(mode="json")})


@m1005_app.command("integrate")
def integrate_command(request: RequestPath) -> None:
    """Execute the deterministic constraint integrator."""

    try:
        parsed = _read_request(request)
        typed = cast("IntegrateProteinRnaConstraintsRequest", parsed)
        result = M1005Service()._execute_validated(typed)
    except M1005ConstraintAuthorizationError as error:
        typer.echo("M10-05 integration failed: caller controls are not accepted", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(
            "M10-05 integration failed: request does not match the declared contract", err=True
        )
        raise typer.Exit(code=1) from error
    _emit(result.model_dump(mode="json"))


@m1005_app.command("verify")
def verify_command(result: RequestPath) -> None:
    """Verify one result receipt and replay its embedded request."""

    try:
        parsed = _read_request(result, result=True)
        typed = cast("ProteinRnaConstraintIntegrationResult", parsed)
        verified = M1005Service().verify(typed)
    except (OSError, StrictJsonError, ValidationError, ValueError) as error:
        typer.echo("M10-05 verification failed: receipt replay verification failed", err=True)
        raise typer.Exit(code=1) from error
    _emit({"verified": True, "result": verified.model_dump(mode="json")})


__all__ = ["create_m1005_app", "m1005_app"]

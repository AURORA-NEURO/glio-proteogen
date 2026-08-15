"""Strict FastAPI and Typer adapters for the provisional M10-04 lane.

This module is intentionally isolated from the legacy aggregate adapters.  The
dossier leaves the endpoint and media catalogue unfrozen, so the route names
and command names below are explicitly provisional and must not be treated as
an ABI commitment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Final, Literal, cast

import typer
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import (
    RequestBodyTooLargeError,
    RequestSizeLimitMiddleware,
)
from glio_proteogen.contracts.m10_04 import (
    M1004_MAX_CANONICAL_REQUEST_BYTES,
    M1004_MAX_CANONICAL_RESULT_BYTES,
    EstimateProteinRnaDiscordanceProbabilisticRequest,
    ProteinRnaDiscordanceProbabilisticResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_04_probabilistic_advanced_estimator import (  # noqa: E501
    M1004ProbabilisticEstimatorAuthorizationError,
    M1004ReplayVerificationError,
    M1004Service,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateProteinRnaDiscordanceProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceProbabilisticResult)
_CONTRACT_NAMES: Final = frozenset(
    {"request", "output", "posterior", "diagnostic", "prior", "constraint", "configuration"}
)


def _validated_json(payload: bytes, *, result: bool = False) -> object:
    """Parse exactly once and then validate the canonicalized JSON document."""

    limit = M1004_MAX_CANONICAL_RESULT_BYTES if result else M1004_MAX_CANONICAL_REQUEST_BYTES
    parsed = strict_json_loads(payload, max_bytes=limit)
    canonical = canonical_json_bytes(parsed)
    adapter = _RESULT_ADAPTER if result else _REQUEST_ADAPTER
    return adapter.validate_json(canonical, strict=True)


def _validation_detail(error: ValidationError) -> list[dict[str, object]]:
    return sanitized_validation_errors(error, location_prefix=("body",))


async def _body(request: Request, *, result: bool = False) -> bytes:
    payload = await request.body()
    limit = M1004_MAX_CANONICAL_RESULT_BYTES if result else M1004_MAX_CANONICAL_REQUEST_BYTES
    if len(payload) > limit:
        raise RequestBodyTooLargeError
    return payload


def create_m1004_app(service: M1004Service | None = None) -> FastAPI:  # noqa: C901
    """Create an isolated provisional M10-04 ASGI application."""

    lane = service or M1004Service()
    app = FastAPI(title="GLIO-PROTEOGEN M10-04 (provisional)", version="0.1.0-provisional")
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=M1004_MAX_CANONICAL_REQUEST_BYTES)

    @app.get("/v1/m10-04/schema/{contract}")
    async def export_schema(contract: str) -> JSONResponse:
        if contract not in _CONTRACT_NAMES:
            return JSONResponse(
                status_code=404,
                content={"detail": "unknown provisional contract"},
            )
        return JSONResponse(content=contract_json_schema(contract))  # type: ignore[arg-type]

    @app.post("/v1/m10-04/validate")
    async def validate(request: Request) -> JSONResponse:
        try:
            parsed = _validated_json(await _body(request))
        except StrictJsonError as error:
            return JSONResponse(
                status_code=400, content={"detail": strict_json_error_detail(error)}
            )
        except ValidationError as error:
            return JSONResponse(status_code=422, content={"detail": _validation_detail(error)})
        except ValueError as error:
            return JSONResponse(status_code=413, content={"detail": str(error)})
        typed = cast("EstimateProteinRnaDiscordanceProbabilisticRequest", parsed)
        return JSONResponse(content={"valid": True, "request": typed.model_dump(mode="json")})

    @app.post("/v1/m10-04/estimate")
    async def estimate(request: Request) -> JSONResponse:
        try:
            parsed = _validated_json(await _body(request))
            typed = cast("EstimateProteinRnaDiscordanceProbabilisticRequest", parsed)
            result = lane.execute(typed)
        except StrictJsonError as error:
            return JSONResponse(
                status_code=400, content={"detail": strict_json_error_detail(error)}
            )
        except ValidationError as error:
            return JSONResponse(status_code=422, content={"detail": _validation_detail(error)})
        except M1004ProbabilisticEstimatorAuthorizationError:
            return JSONResponse(
                status_code=403, content={"detail": "caller controls are not accepted"}
            )
        except ValueError as error:
            return JSONResponse(status_code=413, content={"detail": str(error)})
        return JSONResponse(content=result.model_dump(mode="json"))

    @app.post("/v1/m10-04/verify")
    async def verify(request: Request) -> JSONResponse:
        try:
            parsed = _validated_json(await _body(request, result=True), result=True)
            result = lane.verify(parsed)
        except StrictJsonError as error:
            return JSONResponse(
                status_code=400, content={"detail": strict_json_error_detail(error)}
            )
        except ValidationError:
            return JSONResponse(
                status_code=409, content={"detail": "receipt replay verification failed"}
            )
        except M1004ReplayVerificationError:
            return JSONResponse(
                status_code=409, content={"detail": "receipt replay verification failed"}
            )
        except ValueError as error:
            return JSONResponse(status_code=413, content={"detail": str(error)})
        return JSONResponse(content={"verified": True, "result": result.model_dump(mode="json")})

    return app


RequestPath = Annotated[Path, typer.Argument(exists=True, readable=True, dir_okay=False)]
ContractArgument = Annotated[
    Literal["request", "output", "posterior", "diagnostic", "prior", "constraint", "configuration"],
    typer.Argument(help="Provisional M10-04 contract name."),
]

m1004_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _read_request(path: Path, *, result: bool = False) -> object:
    return _validated_json(path.read_bytes(), result=result)


def _emit(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


@m1004_app.command("export-schema")
def export_schema_command(contract: ContractArgument) -> None:
    """Export one provisional strict JSON Schema."""

    _emit(contract_json_schema(contract))


@m1004_app.command("validate")
def validate_command(request: RequestPath) -> None:
    """Validate one request without executing the estimator."""

    try:
        parsed = _read_request(request)
    except (OSError, StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(
            "M10-04 validation failed: request does not match the declared contract", err=True
        )
        raise typer.Exit(code=2) from error
    typed = cast("EstimateProteinRnaDiscordanceProbabilisticRequest", parsed)
    _emit({"valid": True, "request": typed.model_dump(mode="json")})


@m1004_app.command("estimate")
def estimate_command(request: RequestPath) -> None:
    """Execute the provisional estimator and emit its canonical result."""

    try:
        parsed = _read_request(request)
        typed = cast("EstimateProteinRnaDiscordanceProbabilisticRequest", parsed)
        result = M1004Service().execute(typed)
    except M1004ProbabilisticEstimatorAuthorizationError as error:
        typer.echo("M10-04 estimation failed: caller controls are not accepted", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(
            "M10-04 estimation failed: request does not match the declared contract", err=True
        )
        raise typer.Exit(code=1) from error
    _emit(result.model_dump(mode="json"))


@m1004_app.command("verify")
def verify_command(result: RequestPath) -> None:
    """Verify one result receipt and replay its embedded request."""

    try:
        parsed = _read_request(result, result=True)
        typed = cast("ProteinRnaDiscordanceProbabilisticResult", parsed)
        verified = M1004Service().verify(typed)
    except (OSError, StrictJsonError, ValidationError, ValueError) as error:
        typer.echo("M10-04 verification failed: receipt replay verification failed", err=True)
        raise typer.Exit(code=1) from error
    _emit({"verified": True, "result": verified.model_dump(mode="json")})


__all__ = ["create_m1004_app", "m1004_app"]

"""Strict FastAPI and Typer adapters for provisional M10-06."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Final, Literal, cast

import typer
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestSizeLimitMiddleware, read_bounded
from glio_proteogen.contracts.m10_06 import (
    M1006_MAX_CANONICAL_REQUEST_BYTES,
    M1006_MAX_CANONICAL_RESULT_BYTES,
    DecomposeProteinRnaDiscordanceUncertaintyRequest,
    ProteinRnaDiscordanceUncertaintyDecompositionResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c10_pathway_proteotype_factors.m10_06_uncertainty_decomposition import (
    M1006UncertaintyDecompositionAuthorizationError,
    M1006UncertaintyDecompositionReplayError,
    M1006UncertaintyDecompositionService,
)

_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeProteinRnaDiscordanceUncertaintyRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceUncertaintyDecompositionResult)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "component",
        "decomposition",
        "sensitivity-envelope",
        "policy",
        "finding",
    }
)


def _validated_json(payload: bytes, *, result: bool = False) -> object:
    limit = M1006_MAX_CANONICAL_RESULT_BYTES if result else M1006_MAX_CANONICAL_REQUEST_BYTES
    parsed = strict_json_loads(payload, max_bytes=limit)
    canonical = canonical_json_bytes(parsed)
    adapter = _RESULT_ADAPTER if result else _REQUEST_ADAPTER
    return adapter.validate_json(canonical, strict=True)


def _validation_detail(error: ValidationError) -> list[dict[str, object]]:
    return sanitized_validation_errors(error, location_prefix=("body",))


async def _body(request: Request, *, result: bool = False) -> bytes:
    del result  # Middleware applies the stricter request limit before route parsing.
    return await request.body()


def create_m1006_app(  # noqa: C901
    service: M1006UncertaintyDecompositionService | None = None,
) -> FastAPI:
    """Create an isolated provisional M10-06 ASGI application."""

    lane = service or M1006UncertaintyDecompositionService()
    app = FastAPI(title="GLIO-PROTEOGEN M10-06 (provisional)", version="0.1.0-provisional")
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=M1006_MAX_CANONICAL_REQUEST_BYTES)

    @app.get("/v1/m10-06/schema/{contract}")
    async def export_schema(contract: str) -> JSONResponse:
        if contract not in _CONTRACT_NAMES:
            return JSONResponse(
                status_code=404,
                content={"detail": "unknown provisional contract"},
            )
        return JSONResponse(content=contract_json_schema(contract))  # type: ignore[arg-type]

    @app.post("/v1/m10-06/validate")
    async def validate(request: Request) -> JSONResponse:
        try:
            parsed = _validated_json(await _body(request))
        except StrictJsonError as error:
            return JSONResponse(
                status_code=400, content={"detail": strict_json_error_detail(error)}
            )
        except ValidationError as error:
            return JSONResponse(status_code=422, content={"detail": _validation_detail(error)})
        typed = cast("DecomposeProteinRnaDiscordanceUncertaintyRequest", parsed)
        return JSONResponse(content={"valid": True, "request": typed.model_dump(mode="json")})

    @app.post("/v1/m10-06/decompose")
    async def decompose(request: Request) -> JSONResponse:
        try:
            parsed = _validated_json(await _body(request))
            typed = cast("DecomposeProteinRnaDiscordanceUncertaintyRequest", parsed)
            result = lane.execute(typed)
        except StrictJsonError as error:
            return JSONResponse(
                status_code=400, content={"detail": strict_json_error_detail(error)}
            )
        except ValidationError as error:
            return JSONResponse(status_code=422, content={"detail": _validation_detail(error)})
        except M1006UncertaintyDecompositionAuthorizationError:
            return JSONResponse(
                status_code=403, content={"detail": "caller controls are not accepted"}
            )
        return JSONResponse(content=result.model_dump(mode="json"))

    @app.post("/v1/m10-06/verify")
    async def verify(request: Request) -> JSONResponse:
        try:
            parsed = _validated_json(await _body(request, result=True), result=True)
            typed = cast("ProteinRnaDiscordanceUncertaintyDecompositionResult", parsed)
            result = lane.verify(typed)
        except StrictJsonError as error:
            return JSONResponse(
                status_code=400, content={"detail": strict_json_error_detail(error)}
            )
        except ValidationError:
            return JSONResponse(
                status_code=409, content={"detail": "receipt replay verification failed"}
            )
        except M1006UncertaintyDecompositionReplayError:
            return JSONResponse(
                status_code=409, content={"detail": "receipt replay verification failed"}
            )
        return JSONResponse(content={"verified": True, "result": result.model_dump(mode="json")})

    return app


RequestPath = Annotated[Path, typer.Argument(exists=True, readable=True, dir_okay=False)]
ContractArgument = Annotated[
    Literal[
        "request",
        "output",
        "component",
        "decomposition",
        "sensitivity-envelope",
        "policy",
        "finding",
    ],
    typer.Argument(help="Provisional M10-06 contract name."),
]

m1006_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _read_request(path: Path, *, result: bool = False) -> object:
    max_bytes = M1006_MAX_CANONICAL_RESULT_BYTES if result else M1006_MAX_CANONICAL_REQUEST_BYTES
    return _validated_json(read_bounded(path, max_bytes=max_bytes), result=result)


def _emit(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


@m1006_app.command("export-schema")
def export_schema_command(contract: ContractArgument) -> None:
    """Export one provisional strict JSON Schema."""

    _emit(contract_json_schema(contract))


@m1006_app.command("validate")
def validate_command(request: RequestPath) -> None:
    """Validate one uncertainty-decomposition request."""

    try:
        parsed = _read_request(request)
    except (OSError, StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(
            "M10-06 validation failed: request does not match the declared contract", err=True
        )
        raise typer.Exit(code=2) from error
    typed = cast("DecomposeProteinRnaDiscordanceUncertaintyRequest", parsed)
    _emit({"valid": True, "request": typed.model_dump(mode="json")})


@m1006_app.command("decompose")
def decompose_command(request: RequestPath) -> None:
    """Execute the provisional uncertainty engine."""

    try:
        parsed = _read_request(request)
        typed = cast("DecomposeProteinRnaDiscordanceUncertaintyRequest", parsed)
        result = M1006UncertaintyDecompositionService().execute(typed)
    except M1006UncertaintyDecompositionAuthorizationError as error:
        typer.echo("M10-06 decomposition failed: caller controls are not accepted", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, StrictJsonError, ValidationError, ValueError) as error:
        typer.echo(
            "M10-06 decomposition failed: request does not match the declared contract", err=True
        )
        raise typer.Exit(code=1) from error
    _emit(result.model_dump(mode="json"))


@m1006_app.command("verify")
def verify_command(result: RequestPath) -> None:
    """Verify one result receipt and replay its embedded request."""

    try:
        parsed = _read_request(result, result=True)
        typed = cast("ProteinRnaDiscordanceUncertaintyDecompositionResult", parsed)
        verified = M1006UncertaintyDecompositionService().verify(typed)
    except (OSError, StrictJsonError, ValidationError, ValueError) as error:
        typer.echo("M10-06 verification failed: receipt replay verification failed", err=True)
        raise typer.Exit(code=1) from error
    _emit({"verified": True, "result": verified.model_dump(mode="json")})


__all__ = ["create_m1006_app", "m1006_app"]

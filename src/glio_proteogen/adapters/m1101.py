"""Standalone M11-01 API and CLI adapters.

The M11-01 ABI is still provisional in the dossier.  This adapter therefore
publishes the behavioral contract without changing the shared legacy adapter
surface: JSON is decoded exactly once, controls are checked before opaque
hypothesis traversal, and the private validated execution seam is used by
both HTTP and CLI paths.
"""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves the runtime path type.
from typing import Annotated, Final

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m11_01 import (
    M1101_MAX_CANONICAL_REQUEST_BYTES,
    RegisterVariantPeptideHypothesesRequest,
    VariantPeptideHypothesisRegistryResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)

from ..modules.c11_protein_native_subtype.m11_01_biological_hypothesis_registry.engine import (
    M1101HypothesisAuthorizationError,
    M1101ReplayVerificationError,
)
from ..modules.c11_protein_native_subtype.m11_01_biological_hypothesis_registry.service import (
    M1101Service,
)

_REQUEST_ADAPTER = TypeAdapter(RegisterVariantPeptideHypothesesRequest)
_RESULT_ADAPTER = TypeAdapter(VariantPeptideHypothesisRegistryResult)
_SERVICE = M1101Service()
_INVALID_REQUEST: Final = "invalid M11-01 request"
_OUTPUT_EXISTS: Final = "output already exists"

app = FastAPI(
    title="GLIO-PROTEOGEN M11-01 biological hypothesis registry",
    version="0.1.0-provisional",
)
m1101_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _json_error(status_code: int, detail: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


async def _validated_body(request: Request) -> RegisterVariantPeptideHypothesesRequest:
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != (
        "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        strict_json_loads(
            body,
            max_bytes=M1101_MAX_CANONICAL_REQUEST_BYTES,
        )
        # The strict scanner above enforces duplicate-key/size policy; the
        # contract adapter performs the single typed JSON conversion so date,
        # enum, and tuple fields retain their declared wire representation.
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except StrictJsonError as error:
        raise _json_error(422, "invalid JSON request") from error
    except ValidationError as error:
        raise _json_error(
            422, sanitized_validation_errors(error, location_prefix=("body",))
        ) from error
    except M1101HypothesisAuthorizationError as error:
        raise _json_error(403, str(error)) from error


@app.get("/v1/m11-01/schema/{name}")
def schema(name: str) -> JSONResponse:
    try:
        document = contract_json_schema(name)  # type: ignore[arg-type]
    except (KeyError, ValueError) as error:
        raise _json_error(404, "unknown M11-01 contract schema") from error
    return JSONResponse(document)


@app.post("/v1/modules/M11-01/hypotheses")
async def register(request: Request) -> JSONResponse:
    validated = await _validated_body(request)
    try:
        result = _SERVICE._execute_validated(validated)
    except M1101HypothesisAuthorizationError as error:
        raise _json_error(403, str(error)) from error
    return JSONResponse(result.model_dump(mode="json"))


@app.post("/v1/modules/M11-01/verify")
async def verify(request: Request) -> JSONResponse:
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != (
        "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        strict_json_loads(body, max_bytes=M1101_MAX_CANONICAL_REQUEST_BYTES * 2)
        result = _RESULT_ADAPTER.validate_json(body, strict=True)
        verified = _SERVICE.verify(result)
    except (StrictJsonError, ValidationError, M1101ReplayVerificationError) as error:
        raise _json_error(422, "M11-01 result verification failed") from error
    return JSONResponse(verified.model_dump(mode="json"))


def _load_request(path: Path) -> RegisterVariantPeptideHypothesesRequest:
    try:
        decoded = strict_json_loads(path.read_bytes(), max_bytes=M1101_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_python(decoded, strict=True)
    except (OSError, StrictJsonError, ValidationError) as error:
        raise typer.BadParameter(_INVALID_REQUEST) from error


@m1101_app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="M11-01 schema name.")],
) -> None:
    try:
        typer.echo(json.dumps(contract_json_schema(name), indent=2, sort_keys=True))  # type: ignore[arg-type]
    except (KeyError, ValueError) as error:
        typer.echo("unknown M11-01 schema", err=True)
        raise typer.Exit(code=2) from error


@m1101_app.command("register")
def register_command(
    request_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    if output is not None and output.exists():
        raise typer.BadParameter(_OUTPUT_EXISTS)
    try:
        request = _load_request(request_path)
        result = _SERVICE._execute_validated(request)
        payload = canonical_json_bytes(result).decode("utf-8")
        if output is None:
            typer.echo(payload)
        else:
            output.write_text(payload + "\n", encoding="utf-8", newline="\n")
    except (M1101HypothesisAuthorizationError, OSError, typer.BadParameter) as error:
        typer.echo(f"registration failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@m1101_app.command("verify")
def verify_command(
    result_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    try:
        decoded = strict_json_loads(
            result_path.read_bytes(),
            max_bytes=M1101_MAX_CANONICAL_REQUEST_BYTES * 2,
        )
        result = _RESULT_ADAPTER.validate_python(decoded, strict=True)
        verified = _SERVICE.verify(result)
    except (OSError, StrictJsonError, ValidationError, M1101ReplayVerificationError) as error:
        typer.echo("verification failed: M11-01 result is invalid", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(canonical_json_bytes(verified).decode("utf-8"))


__all__ = ["app", "m1101_app"]

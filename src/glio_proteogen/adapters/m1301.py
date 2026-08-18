"""Standalone M13-01 HTTP and CLI adapters with strict parse-once semantics."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves the runtime path type.
from typing import Annotated, Final

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.contracts.m13_01 import (
    M1301_MAX_CANONICAL_REQUEST_BYTES,
    M1301_MAX_CANONICAL_RESULT_BYTES,
    ProteotypeHypothesisRegistryResult,
    RegisterProteotypeHypothesesRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)

from ..modules.c11_protein_native_subtype.m13_01_biological_hypothesis_registry.engine import (
    M1301HypothesisAuthorizationError,
    M1301ReplayVerificationError,
    preflight_hypothesis_authorization,
)
from ..modules.c11_protein_native_subtype.m13_01_biological_hypothesis_registry.service import (
    M1301Service,
)

_REQUEST_ADAPTER = TypeAdapter(RegisterProteotypeHypothesesRequest)
_RESULT_ADAPTER = TypeAdapter(ProteotypeHypothesisRegistryResult)
_SERVICE = M1301Service()
_INVALID_REQUEST: Final = "invalid M13-01 request"
_OUTPUT_EXISTS: Final = "output already exists"

app = FastAPI(
    title="GLIO-PROTEOGEN M13-01 biological hypothesis registry",
    version="0.1.0-provisional",
)
m1301_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _json_error(status_code: int, detail: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


async def _validated_body(request: Request) -> RegisterProteotypeHypothesesRequest:
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != (
        "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        decoded = strict_json_loads(body, max_bytes=M1301_MAX_CANONICAL_REQUEST_BYTES)
        preflight_hypothesis_authorization(decoded)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    except StrictJsonError as error:
        raise _json_error(422, "invalid JSON request") from error
    except ValidationError as error:
        raise _json_error(
            422, sanitized_validation_errors(error, location_prefix=("body",))
        ) from error
    except M1301HypothesisAuthorizationError as error:
        raise _json_error(403, str(error)) from error


@app.get("/v1/m13-01/schema/{name}")
def schema(name: str) -> JSONResponse:
    try:
        document = contract_json_schema(name)  # type: ignore[arg-type]
    except (KeyError, ValueError) as error:
        raise _json_error(404, "unknown M13-01 contract schema") from error
    return JSONResponse(document)


@app.post("/v1/modules/M13-01/hypotheses")
async def register(request: Request) -> JSONResponse:
    validated = await _validated_body(request)
    try:
        result = _SERVICE._execute_validated(validated)
    except M1301HypothesisAuthorizationError as error:
        raise _json_error(403, str(error)) from error
    return JSONResponse(result.model_dump(mode="json"))


@app.post("/v1/modules/M13-01/verify")
async def verify(request: Request) -> JSONResponse:
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != (
        "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        decoded = strict_json_loads(body, max_bytes=M1301_MAX_CANONICAL_RESULT_BYTES)
        result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        verified = _SERVICE.verify(result)
    except (StrictJsonError, ValidationError, M1301ReplayVerificationError) as error:
        raise _json_error(422, "M13-01 result verification failed") from error
    return JSONResponse(verified.model_dump(mode="json"))


def _load_request(path: Path) -> RegisterProteotypeHypothesesRequest:
    try:
        raw = read_bounded(path, M1301_MAX_CANONICAL_REQUEST_BYTES)
        decoded = strict_json_loads(raw, max_bytes=M1301_MAX_CANONICAL_REQUEST_BYTES)
        preflight_hypothesis_authorization(decoded)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    except (
        OSError,
        RequestBodyTooLargeError,
        StrictJsonError,
        ValidationError,
        M1301HypothesisAuthorizationError,
    ) as error:
        raise typer.BadParameter(_INVALID_REQUEST) from error


def _read_result(path: Path) -> bytes:
    return read_bounded(path, M1301_MAX_CANONICAL_RESULT_BYTES)


@m1301_app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="M13-01 schema name.")],
) -> None:
    try:
        typer.echo(json.dumps(contract_json_schema(name), indent=2, sort_keys=True))  # type: ignore[arg-type]
    except (KeyError, ValueError) as error:
        typer.echo("unknown M13-01 schema", err=True)
        raise typer.Exit(code=2) from error


@m1301_app.command("register")
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
    except (M1301HypothesisAuthorizationError, OSError, typer.BadParameter) as error:
        typer.echo(f"registration failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@m1301_app.command("verify")
def verify_command(
    result_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    try:
        raw = _read_result(result_path)
        decoded = strict_json_loads(raw, max_bytes=M1301_MAX_CANONICAL_RESULT_BYTES)
        result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
        verified = _SERVICE.verify(result)
    except (
        OSError,
        RequestBodyTooLargeError,
        StrictJsonError,
        ValidationError,
        M1301ReplayVerificationError,
    ) as error:
        typer.echo("verification failed: M13-01 result is invalid", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(canonical_json_bytes(verified).decode("utf-8"))


__all__ = ["app", "m1301_app"]

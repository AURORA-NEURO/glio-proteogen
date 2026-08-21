"""Standalone provisional M16-08 FastAPI and Typer adapters."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves this runtime type.
from typing import Annotated, Final

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import (
    RequestBodyTooLargeError,
    RequestSizeLimitMiddleware,
    read_bounded,
)
from glio_proteogen.contracts.m16_08 import (
    M1608_MAX_CANONICAL_REQUEST_BYTES,
    M1608_MAX_CANONICAL_RESULT_BYTES,
    MonitorProteinRnaTranslationHealthRequest,
    ProteinRnaDiscordanceTranslationHealthResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c16_protein_rna_discordance import (
    m16_08_translation_monitoring_rollback as _m1608,
)

_REQUEST_ADAPTER = TypeAdapter(MonitorProteinRnaTranslationHealthRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinRnaDiscordanceTranslationHealthResult)
_SERVICE = _m1608.M1608Service()
_INVALID_REQUEST: Final = "invalid M16-08 request"
_OUTPUT_EXISTS: Final = "output already exists"

app = FastAPI(title="GLIO-PROTEOGEN M16-08 translation monitoring", version="0.1.0-provisional")
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=M1608_MAX_CANONICAL_REQUEST_BYTES,
    result_max_bytes=M1608_MAX_CANONICAL_RESULT_BYTES,
)
m1608_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _json_error(status_code: int, detail: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


async def _validated_body(request: Request) -> MonitorProteinRnaTranslationHealthRequest:
    if (
        request.headers.get("content-type", "").partition(";")[0].strip().lower()
        != "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        decoded = strict_json_loads(body, max_bytes=M1608_MAX_CANONICAL_REQUEST_BYTES)
        _m1608.preflight_m1608_authorization(decoded)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except StrictJsonError as error:
        raise _json_error(422, "invalid JSON request") from error
    except ValidationError as error:
        raise _json_error(
            422, sanitized_validation_errors(error, location_prefix=("body",))
        ) from error
    except _m1608.M1608AuthorizationError as error:
        raise _json_error(403, str(error)) from error


@app.get("/v1/m16-08/schema/{name}")
def schema(name: str) -> JSONResponse:
    try:
        document = contract_json_schema(name)  # type: ignore[arg-type]
    except (KeyError, ValueError) as error:
        raise _json_error(404, "unknown M16-08 contract schema") from error
    return JSONResponse(document)


@app.post("/v1/modules/M16-08/monitor")
async def monitor(request: Request) -> JSONResponse:
    validated = await _validated_body(request)
    try:
        result = _SERVICE._execute_validated(validated)
    except _m1608.M1608AuthorizationError as error:
        raise _json_error(403, str(error)) from error
    return JSONResponse(result.model_dump(mode="json"))


@app.post("/v1/modules/M16-08/verify")
async def verify(request: Request) -> JSONResponse:
    if (
        request.headers.get("content-type", "").partition(";")[0].strip().lower()
        != "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        strict_json_loads(body, max_bytes=M1608_MAX_CANONICAL_RESULT_BYTES)
        result = _RESULT_ADAPTER.validate_json(body, strict=True)
        verified = _SERVICE.verify(result)
    except (StrictJsonError, ValidationError, _m1608.M1608ReplayVerificationError) as error:
        raise _json_error(422, "M16-08 result verification failed") from error
    return JSONResponse(verified.model_dump(mode="json"))


def _load_request(path: Path) -> MonitorProteinRnaTranslationHealthRequest:
    try:
        raw = read_bounded(path, M1608_MAX_CANONICAL_REQUEST_BYTES)
        decoded = strict_json_loads(raw, max_bytes=M1608_MAX_CANONICAL_REQUEST_BYTES)
        _m1608.preflight_m1608_authorization(decoded)
        return _REQUEST_ADAPTER.validate_json(raw, strict=True)
    except (
        OSError,
        RequestBodyTooLargeError,
        StrictJsonError,
        ValidationError,
        _m1608.M1608AuthorizationError,
    ) as error:
        raise typer.BadParameter(_INVALID_REQUEST) from error


def _read_result(path: Path) -> bytes:
    return read_bounded(path, M1608_MAX_CANONICAL_RESULT_BYTES)


@m1608_app.command("export-schema")
def export_schema(name: Annotated[str, typer.Argument(help="M16-08 schema name.")]) -> None:
    try:
        typer.echo(json.dumps(contract_json_schema(name), indent=2, sort_keys=True))  # type: ignore[arg-type]
    except (KeyError, ValueError) as error:
        typer.echo("unknown M16-08 schema", err=True)
        raise typer.Exit(code=2) from error


@m1608_app.command("monitor")
def monitor_command(
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
    except (_m1608.M1608AuthorizationError, OSError, typer.BadParameter) as error:
        typer.echo(f"monitoring failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@m1608_app.command("verify")
def verify_command(
    result_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    try:
        raw = _read_result(result_path)
        strict_json_loads(raw, max_bytes=M1608_MAX_CANONICAL_RESULT_BYTES)
        result = _RESULT_ADAPTER.validate_json(raw, strict=True)
        verified = _SERVICE.verify(result)
    except (
        OSError,
        RequestBodyTooLargeError,
        StrictJsonError,
        ValidationError,
        _m1608.M1608ReplayVerificationError,
    ) as error:
        typer.echo("verification failed: M16-08 result is invalid", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(canonical_json_bytes(verified).decode("utf-8"))


__all__ = ["app", "m1608_app"]

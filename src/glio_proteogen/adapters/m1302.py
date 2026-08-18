"""Standalone FastAPI and Typer boundaries for provisional M13-02."""

from __future__ import annotations

import json
import sys
from pathlib import Path  # noqa: TC003 - Typer requires the runtime Path type.
from typing import Annotated, Any

import typer
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from glio_proteogen.adapters.limits import (
    RequestBodyTooLargeError,
    RequestSizeLimitMiddleware,
    read_bounded,
)
from glio_proteogen.contracts.m13_02 import (
    M1302_MAX_CANONICAL_REQUEST_BYTES,
    M1302_MAX_CANONICAL_RESULT_BYTES,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c11_protein_native_subtype.m13_02_context_subtype_stratifier import (
    M1302AuthorizationError,
    M1302Plugin,
    M1302Service,
    verify_context_result,
)

_service = M1302Service()
_plugin = M1302Plugin(_service)


def _error(status: int, code: str, message: str, details: object = None) -> JSONResponse:
    body: dict[str, object] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"] = {**body["error"], "details": details}  # type: ignore[dict-item]
    return JSONResponse(status_code=status, content=body)


async def _decoded_body(request: Request) -> dict[str, Any] | JSONResponse:
    try:
        decoded = strict_json_loads(
            await request.body(), max_bytes=M1302_MAX_CANONICAL_REQUEST_BYTES
        )
    except StrictJsonError as exc:
        return _error(400, exc.code.value, str(exc), strict_json_error_detail(exc))
    if not isinstance(decoded, dict):
        return _error(422, "request_object_required", "request must be a JSON object")
    return decoded


app = FastAPI(title="GLIO-PROTEOGEN M13-02", version="0.1.0-provisional")
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=M1302_MAX_CANONICAL_REQUEST_BYTES,
)


@app.get("/v1/m13-02/schema/{name}", response_model=None)
def export_schema(name: str) -> dict[str, object] | JSONResponse:
    if name not in {
        "request",
        "output",
        "observation",
        "profile",
        "mechanism",
        "mechanism-candidate",
        "configuration",
        "policy",
        "finding",
    }:
        return _error(404, "unknown_schema", "schema name is not declared")
    return contract_json_schema(name)  # type: ignore[arg-type]


@app.post("/v1/modules/M13-02/context")
async def stratify_context(request: Request) -> JSONResponse:
    decoded = await _decoded_body(request)
    if isinstance(decoded, JSONResponse):
        return decoded
    try:
        token = _plugin.validate(decoded)
        result = _plugin.run(token)
    except M1302AuthorizationError as exc:
        return _error(403, "authorization_required", str(exc))
    except ValidationError as exc:
        return _error(
            422,
            "contract_validation_failed",
            "request does not match contract",
            sanitized_validation_errors(exc),
        )
    except (TypeError, ValueError) as exc:
        return _error(422, "contract_validation_failed", str(exc))
    return JSONResponse(content=result.model_dump(mode="json"))


@app.post("/v1/modules/M13-02/verify")
async def verify_context(request: Request) -> JSONResponse:
    decoded = await _decoded_body(request)
    if isinstance(decoded, JSONResponse):
        return decoded
    if not verify_context_result(decoded):
        return _error(
            422,
            "replay_verification_failed",
            "result envelope failed replay verification",
        )
    return JSONResponse(content={"verified": True})


m1302_app = typer.Typer(add_completion=False, no_args_is_help=True)


def _read_input(path: Path, max_bytes: int) -> bytes:
    if str(path) == "-":
        payload = sys.stdin.buffer.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise RequestBodyTooLargeError
        return payload
    return read_bounded(path, max_bytes)


def _write_json(value: object, output: Path | None) -> None:
    encoded = canonical_json_bytes(value)
    if output is None:
        typer.echo(encoded.decode("utf-8"))
        return
    if output.exists():
        raise typer.BadParameter(  # noqa: TRY003 - Typer renders this user-facing diagnostic.
            "output exists; refusing overwrite", param_hint="output"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)


@m1302_app.command("export-schema")
def cli_export_schema(
    name: Annotated[str, typer.Argument(help="request, output, or component schema name")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    names = {
        "request",
        "output",
        "observation",
        "profile",
        "mechanism",
        "mechanism-candidate",
        "configuration",
        "policy",
        "finding",
    }
    if name not in names:
        raise typer.BadParameter(  # noqa: TRY003 - Typer renders this user-facing diagnostic.
            "schema name is not declared", param_hint="name"
        )
    _write_json(contract_json_schema(name), output)  # type: ignore[arg-type]


@m1302_app.command("stratify")
def cli_stratify(
    input_path: Annotated[Path, typer.Argument(help="request JSON path, or '-' for stdin")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    try:
        decoded = strict_json_loads(
            _read_input(input_path, M1302_MAX_CANONICAL_REQUEST_BYTES),
            max_bytes=M1302_MAX_CANONICAL_REQUEST_BYTES,
        )
        if not isinstance(decoded, dict):
            raise typer.BadParameter(  # noqa: TRY003 - Typer renders this user-facing diagnostic.
                "request must be a JSON object", param_hint="input"
            )
        token = _plugin.validate(decoded)
        result = _plugin.run(token)
    except RequestBodyTooLargeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    except StrictJsonError as exc:
        typer.echo(json.dumps(strict_json_error_detail(exc), sort_keys=True), err=True)
        raise typer.Exit(2) from exc
    except M1302AuthorizationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(3) from exc
    except ValidationError as exc:
        typer.echo(json.dumps(sanitized_validation_errors(exc), sort_keys=True), err=True)
        raise typer.Exit(2) from exc
    _write_json(result.model_dump(mode="json"), output)


@m1302_app.command("verify")
def cli_verify(
    input_path: Annotated[Path, typer.Argument(help="result JSON path, or '-' for stdin")],
) -> None:
    try:
        decoded = strict_json_loads(
            _read_input(input_path, M1302_MAX_CANONICAL_RESULT_BYTES),
            max_bytes=M1302_MAX_CANONICAL_RESULT_BYTES,
        )
    except RequestBodyTooLargeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    except StrictJsonError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    if not verify_context_result(decoded):
        typer.echo("result envelope failed replay verification", err=True)
        raise typer.Exit(1)
    typer.echo("verified")


__all__ = ["app", "m1302_app"]

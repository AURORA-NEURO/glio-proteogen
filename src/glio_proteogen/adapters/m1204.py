"""Standalone provisional M12-04 FastAPI and Typer adapters.

Both surfaces use one strict JSON scanner and service seam.  Controls are
checked on the decoded object before typed conversion can traverse opaque
artifact-backed mechanism material.
"""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves this runtime type.
from typing import Annotated, Final

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestSizeLimitMiddleware, read_bounded
from glio_proteogen.contracts.m12_04 import (
    M1204_MAX_CANONICAL_REQUEST_BYTES,
    M1204_MAX_CANONICAL_RESULT_BYTES,
    BiomarkerPanelMechanismInferenceResult,
    InferBiomarkerPanelMechanismRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c12_driver_to_protein_consequence.m12_04_network_state_mechanism_inference import (  # noqa: E501
    M1204MechanismAuthorizationError,
    M1204ReplayVerificationError,
    M1204Service,
    preflight_mechanism_authorization,
)

_REQUEST_ADAPTER = TypeAdapter(InferBiomarkerPanelMechanismRequest)
_RESULT_ADAPTER = TypeAdapter(BiomarkerPanelMechanismInferenceResult)
_SERVICE = M1204Service()
_INVALID_REQUEST: Final = "invalid M12-04 request"
_OUTPUT_EXISTS: Final = "output already exists"

app = FastAPI(
    title="GLIO-PROTEOGEN M12-04 network/state/mechanism inference",
    version="0.1.0-provisional",
)
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=M1204_MAX_CANONICAL_REQUEST_BYTES,
    result_max_bytes=M1204_MAX_CANONICAL_RESULT_BYTES,
)
m1204_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _json_error(status_code: int, detail: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


async def _validated_body(request: Request) -> InferBiomarkerPanelMechanismRequest:
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != (
        "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        decoded = strict_json_loads(body, max_bytes=M1204_MAX_CANONICAL_REQUEST_BYTES)
        preflight_mechanism_authorization(decoded)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except StrictJsonError as error:
        raise _json_error(422, "invalid JSON request") from error
    except ValidationError as error:
        raise _json_error(
            422, sanitized_validation_errors(error, location_prefix=("body",))
        ) from error
    except M1204MechanismAuthorizationError as error:
        raise _json_error(403, str(error)) from error


@app.get("/v1/m12-04/schema/{name}")
def schema(name: str) -> JSONResponse:
    try:
        document = contract_json_schema(name)  # type: ignore[arg-type]
    except (KeyError, ValueError) as error:
        raise _json_error(404, "unknown M12-04 contract schema") from error
    return JSONResponse(document)


@app.post("/v1/modules/M12-04/mechanism")
async def infer(request: Request) -> JSONResponse:
    validated = await _validated_body(request)
    try:
        result = _SERVICE._execute_validated(validated)
    except M1204MechanismAuthorizationError as error:
        raise _json_error(403, str(error)) from error
    return JSONResponse(result.model_dump(mode="json"))


@app.post("/v1/modules/M12-04/verify")
async def verify(request: Request) -> JSONResponse:
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != (
        "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        strict_json_loads(body, max_bytes=M1204_MAX_CANONICAL_RESULT_BYTES)
        result = _RESULT_ADAPTER.validate_json(body, strict=True)
        verified = _SERVICE.verify(result)
    except (StrictJsonError, ValidationError, M1204ReplayVerificationError) as error:
        raise _json_error(422, "M12-04 result verification failed") from error
    return JSONResponse(verified.model_dump(mode="json"))


def _load_request(path: Path) -> InferBiomarkerPanelMechanismRequest:
    try:
        raw = read_bounded(path, M1204_MAX_CANONICAL_REQUEST_BYTES)
        decoded = strict_json_loads(raw, max_bytes=M1204_MAX_CANONICAL_REQUEST_BYTES)
        preflight_mechanism_authorization(decoded)
        return _REQUEST_ADAPTER.validate_json(raw, strict=True)
    except (OSError, StrictJsonError, ValidationError, M1204MechanismAuthorizationError) as error:
        raise typer.BadParameter(_INVALID_REQUEST) from error


@m1204_app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="M12-04 schema name.")],
) -> None:
    try:
        typer.echo(json.dumps(contract_json_schema(name), indent=2, sort_keys=True))  # type: ignore[arg-type]
    except (KeyError, ValueError) as error:
        typer.echo("unknown M12-04 schema", err=True)
        raise typer.Exit(code=2) from error


@m1204_app.command("infer")
def infer_command(
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
    except (M1204MechanismAuthorizationError, OSError, typer.BadParameter) as error:
        typer.echo(f"inference failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@m1204_app.command("verify")
def verify_command(
    result_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    try:
        raw = read_bounded(result_path, M1204_MAX_CANONICAL_RESULT_BYTES)
        strict_json_loads(raw, max_bytes=M1204_MAX_CANONICAL_RESULT_BYTES)
        result = _RESULT_ADAPTER.validate_json(raw, strict=True)
        verified = _SERVICE.verify(result)
    except (OSError, StrictJsonError, ValidationError, M1204ReplayVerificationError) as error:
        typer.echo("verification failed: M12-04 result is invalid", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(canonical_json_bytes(verified).decode("utf-8"))


__all__ = ["app", "m1204_app"]

"""Standalone provisional M14-08 FastAPI and Typer adapters.

Both surfaces use the same strict JSON scanner and service seam.  Controls are
checked on the decoded object before the typed conversion can traverse any
opaque artifact-backed dossier material.
"""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves this runtime type.
from typing import Annotated, Final

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m14_08 import (
    M1408_MAX_CANONICAL_REQUEST_BYTES,
    ProteinSubtypeMechanismEvidenceDossierResult,
    PublishProteinSubtypeMechanismDossierRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c14_microenvironment_protein_deconvolution.m14_08_mechanism_evidence_dossier import (  # noqa: E501
    M1408DossierAuthorizationError,
    M1408ReplayVerificationError,
    M1408Service,
    preflight_dossier_authorization,
)

_REQUEST_ADAPTER = TypeAdapter(PublishProteinSubtypeMechanismDossierRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypeMechanismEvidenceDossierResult)
_SERVICE = M1408Service()
_INVALID_REQUEST: Final = "invalid M14-08 request"
_OUTPUT_EXISTS: Final = "output already exists"

app = FastAPI(
    title="GLIO-PROTEOGEN M14-08 network/state/dossier inference",
    version="0.1.0-provisional",
)
m1408_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _json_error(status_code: int, detail: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


async def _validated_body(request: Request) -> PublishProteinSubtypeMechanismDossierRequest:
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != (
        "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        decoded = strict_json_loads(body, max_bytes=M1408_MAX_CANONICAL_REQUEST_BYTES)
        preflight_dossier_authorization(decoded)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except StrictJsonError as error:
        raise _json_error(422, "invalid JSON request") from error
    except ValidationError as error:
        raise _json_error(
            422, sanitized_validation_errors(error, location_prefix=("body",))
        ) from error
    except M1408DossierAuthorizationError as error:
        raise _json_error(403, str(error)) from error


@app.get("/v1/m14-08/schema/{name}")
def schema(name: str) -> JSONResponse:
    try:
        document = contract_json_schema(name)  # type: ignore[arg-type]
    except (KeyError, ValueError) as error:
        raise _json_error(404, "unknown M14-08 contract schema") from error
    return JSONResponse(document)


@app.post("/v1/modules/M14-08/dossier")
async def infer(request: Request) -> JSONResponse:
    validated = await _validated_body(request)
    try:
        result = _SERVICE._execute_validated(validated)
    except M1408DossierAuthorizationError as error:
        raise _json_error(403, str(error)) from error
    return JSONResponse(result.model_dump(mode="json"))


@app.post("/v1/modules/M14-08/verify")
async def verify(request: Request) -> JSONResponse:
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != (
        "application/json"
    ):
        raise _json_error(415, "content-type must be application/json")
    try:
        body = await request.body()
        strict_json_loads(body, max_bytes=M1408_MAX_CANONICAL_REQUEST_BYTES * 2)
        result = _RESULT_ADAPTER.validate_json(body, strict=True)
        verified = _SERVICE.verify(result)
    except (StrictJsonError, ValidationError, M1408ReplayVerificationError) as error:
        raise _json_error(422, "M14-08 result verification failed") from error
    return JSONResponse(verified.model_dump(mode="json"))


def _load_request(path: Path) -> PublishProteinSubtypeMechanismDossierRequest:
    try:
        raw = path.read_bytes()
        decoded = strict_json_loads(raw, max_bytes=M1408_MAX_CANONICAL_REQUEST_BYTES)
        preflight_dossier_authorization(decoded)
        return _REQUEST_ADAPTER.validate_json(raw, strict=True)
    except (OSError, StrictJsonError, ValidationError, M1408DossierAuthorizationError) as error:
        raise typer.BadParameter(_INVALID_REQUEST) from error


@m1408_app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="M14-08 schema name.")],
) -> None:
    try:
        typer.echo(json.dumps(contract_json_schema(name), indent=2, sort_keys=True))  # type: ignore[arg-type]
    except (KeyError, ValueError) as error:
        typer.echo("unknown M14-08 schema", err=True)
        raise typer.Exit(code=2) from error


@m1408_app.command("infer")
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
    except (M1408DossierAuthorizationError, OSError, typer.BadParameter) as error:
        typer.echo(f"inference failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@m1408_app.command("verify")
def verify_command(
    result_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    try:
        raw = result_path.read_bytes()
        strict_json_loads(raw, max_bytes=M1408_MAX_CANONICAL_REQUEST_BYTES * 2)
        result = _RESULT_ADAPTER.validate_json(raw, strict=True)
        verified = _SERVICE.verify(result)
    except (OSError, StrictJsonError, ValidationError, M1408ReplayVerificationError) as error:
        typer.echo("verification failed: M14-08 result is invalid", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(canonical_json_bytes(verified).decode("utf-8"))


__all__ = ["app", "m1408_app"]

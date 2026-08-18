"""Standalone FastAPI and Typer adapters for provisional M11-03."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003
from typing import Annotated, cast

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m11_03 import (
    M1103_MAX_CANONICAL_REQUEST_BYTES,
    M1103_MAX_CANONICAL_RESULT_BYTES,
    ContractName,
    VariantPeptideMechanisticFeatureResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c11_protein_native_subtype.m11_03_mechanistic_feature_constructor import (  # noqa: E501
    M1103AuthorizationError,
    M1103Service,
    verify_m1103_replay,
)
from glio_proteogen.modules.c11_protein_native_subtype.m11_03_mechanistic_feature_constructor.engine import (  # noqa: E501
    _validate_json_request,
)


class _OutputExistsError(FileExistsError):
    def __init__(self) -> None:
        super().__init__("output already exists")


app = FastAPI(title="GLIO-PROTEOGEN M11-03", version="0.1.0-provisional")
m1103_app = typer.Typer(help="M11-03 mechanistic feature constructor commands.")


def _error(status: int, detail: object) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


async def _body(request: Request, max_bytes: int) -> tuple[object, bytes]:
    raw = await request.body()
    try:
        return strict_json_loads(raw, max_bytes=max_bytes), raw
    except StrictJsonError as error:
        raise HTTPException(
            status_code=400,
            detail=strict_json_error_detail(error),
        ) from error


@app.get("/v1/m11-03/schema/{name}")
async def export_schema(name: str) -> dict[str, object]:
    try:
        return contract_json_schema(cast("ContractName", name))
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=404, detail="unknown M11-03 contract") from error


async def _construct(request: Request) -> JSONResponse:
    decoded, raw = await _body(request, M1103_MAX_CANONICAL_REQUEST_BYTES)
    try:
        typed = _validate_json_request(decoded, raw)
        result = M1103Service().execute(typed)
    except M1103AuthorizationError as error:
        return _error(403, str(error))
    except ValidationError as error:
        return _error(422, sanitized_validation_errors(error))
    except (TypeError, ValueError) as error:
        return _error(422, str(error))
    return JSONResponse(content=json.loads(canonical_json_bytes(result)))


@app.post("/v1/modules/M11-03/mechanistic-features")
async def construct(request: Request) -> JSONResponse:
    return await _construct(request)


@app.post("/v1/modules/GLIO-PROTEOGEN-M11-03/construct")
async def construct_alias(request: Request) -> JSONResponse:
    return await _construct(request)


@app.post("/v1/modules/M11-03/verify")
async def verify(request: Request) -> JSONResponse:
    decoded, _raw = await _body(request, M1103_MAX_CANONICAL_RESULT_BYTES)
    if type(decoded) is not dict:
        return _error(422, "verify body must be an object containing request and result")
    body = cast("dict[str, object]", decoded)
    request_value = body.get("request")
    result_value = body.get("result")
    if type(request_value) is not dict or type(result_value) is not dict:
        return _error(422, "verify body must contain request and result objects")
    try:
        typed_request = _validate_json_request(request_value, canonical_json_bytes(request_value))
        typed_result = VariantPeptideMechanisticFeatureResult.model_validate_json(
            canonical_json_bytes(result_value), strict=True
        )
    except M1103AuthorizationError as error:
        return _error(403, str(error))
    except ValidationError as error:
        return _error(422, sanitized_validation_errors(error))
    except (TypeError, ValueError) as error:
        return _error(422, str(error))
    return JSONResponse(content={"verified": verify_m1103_replay(typed_result, typed_request)})


def _read_json(path: Path, max_bytes: int) -> tuple[object, bytes]:
    raw = read_bounded(path, max_bytes)
    return strict_json_loads(raw, max_bytes=max_bytes), raw


def _write_new(path: Path, value: object) -> None:
    if path.exists():
        raise _OutputExistsError
    path.write_bytes(canonical_json_bytes(value))


@m1103_app.command("export-schema")
def cli_export_schema(
    name: Annotated[str, typer.Argument(help="Contract name exported as JSON Schema.")],
) -> None:
    try:
        typer.echo(
            json.dumps(contract_json_schema(cast("ContractName", name)), indent=2, sort_keys=True)
        )
    except (KeyError, ValueError) as error:
        typer.echo("unknown M11-03 contract", err=True)
        raise typer.Exit(code=2) from error


@m1103_app.command("construct")
def cli_construct(
    request: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    try:
        decoded, raw = _read_json(request, M1103_MAX_CANONICAL_REQUEST_BYTES)
        typed = _validate_json_request(decoded, raw)
        result = M1103Service().execute(typed)
        payload = result.model_dump(mode="json")
        if output is not None:
            _write_new(output, payload)
        else:
            typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        if result.status.value != "constructed":
            raise typer.Exit(code=1)
    except M1103AuthorizationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    except (OSError, StrictJsonError, TypeError, ValueError, ValidationError) as error:
        typer.echo("M11-03 construction failed: " + str(error), err=True)
        raise typer.Exit(code=1) from error


@m1103_app.command("verify")
def cli_verify(
    request: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    result: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    try:
        request_value, request_raw = _read_json(request, M1103_MAX_CANONICAL_REQUEST_BYTES)
        _ = request_raw
        result_value, _ = _read_json(result, M1103_MAX_CANONICAL_RESULT_BYTES)
        typed_request = _validate_json_request(request_value, canonical_json_bytes(request_value))
        typed_result = VariantPeptideMechanisticFeatureResult.model_validate(
            result_value, strict=False
        )
        verified = verify_m1103_replay(typed_result, typed_request)
        typer.echo(json.dumps({"verified": verified}, sort_keys=True))
        if not verified:
            raise typer.Exit(code=1)
    except (OSError, StrictJsonError, TypeError, ValueError, ValidationError) as error:
        typer.echo("M11-03 verification failed: " + str(error), err=True)
        raise typer.Exit(code=1) from error


__all__ = ["app", "m1103_app"]

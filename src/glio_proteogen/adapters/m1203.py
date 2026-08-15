"""Standalone FastAPI and Typer adapters for provisional M12-03."""

from __future__ import annotations

import json
import pathlib  # noqa: TC003 - Path is used at runtime for CLI filesystem access.
from typing import Annotated, Final, cast

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from glio_proteogen.contracts.m12_03 import (
    M1203_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelMechanisticFeatureResult,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c12_driver_protein_consequence import (
    M1203Service,
    construct_mechanistic_features,
    validate_json_request,
)

_SERVICE: Final = M1203Service()
app = FastAPI(title="GLIO-PROTEOGEN M12-03", version="0.1.0-provisional")
m1203_app = typer.Typer(add_completion=False, no_args_is_help=True)
_SCHEMA_NAMES: Final = (
    "request",
    "output",
    "feature-object",
    "feature",
    "lineage",
    "relation",
    "configuration",
    "diagnostic",
)


class _CliSchemaError(typer.BadParameter):
    def __init__(self) -> None:
        super().__init__("unknown M12-03 schema")


class _CliOverwriteError(typer.BadParameter):
    def __init__(self) -> None:
        super().__init__("refusing to overwrite existing schema file")


class _CliRequestError(typer.BadParameter):
    def __init__(self) -> None:
        super().__init__("M12-03 request failed strict validation")


class _CliResultError(typer.BadParameter):
    def __init__(self) -> None:
        super().__init__("M12-03 result failed replay verification")


def _error(message: str, status_code: int = 422) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": "M1203_INVALID_REQUEST", "message": message}},
    )


@app.exception_handler(ValidationError)
async def _validation_error(_request: Request, _exc: ValidationError) -> JSONResponse:
    return _error("M12-03 request failed strict validation")


@app.get("/v1/m12-03/schema/{name}")
def export_schema(name: str) -> dict[str, object]:
    if name not in _SCHEMA_NAMES:
        raise HTTPException(status_code=404, detail="unknown M12-03 schema")
    return contract_json_schema(name)  # type: ignore[arg-type]


@app.post("/v1/modules/M12-03/construct")
async def construct(request: Request) -> JSONResponse:
    raw = await request.body()
    try:
        decoded = strict_json_loads(raw, max_bytes=M1203_MAX_CANONICAL_REQUEST_BYTES)
        typed = validate_json_request(decoded, raw)
        result = _SERVICE.execute(typed)
    except (ValueError, TypeError, ValidationError):
        return _error("M12-03 request failed strict validation")
    return JSONResponse(result.model_dump(mode="json"))


@app.post("/v1/modules/M12-03/verify")
async def verify(request: Request) -> JSONResponse:
    raw = await request.body()
    try:
        decoded = strict_json_loads(raw, max_bytes=8 * 1024 * 1024)
        result = BiomarkerPanelMechanisticFeatureResult.model_validate(decoded)
    except (ValueError, TypeError, ValidationError):
        return _error("M12-03 result failed replay verification")
    return JSONResponse(
        {
            "moduleId": "GLIO-PROTEOGEN-M12-03",
            "verified": True,
            "resultId": result.result_id,
            "resultDigest": result.result_digest,
        }
    )


def _read_json(path: pathlib.Path) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        strict_json_loads(path.read_bytes(), max_bytes=M1203_MAX_CANONICAL_REQUEST_BYTES),
    )


@m1203_app.command("export-schema")
def cli_export_schema(
    name: Annotated[str, typer.Argument(help="Schema name")],
    output: Annotated[pathlib.Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    if name not in _SCHEMA_NAMES:
        raise _CliSchemaError
    payload = contract_json_schema(name)  # type: ignore[arg-type]
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is None:
        typer.echo(encoded, nl=False)
    else:
        if output.exists():
            raise _CliOverwriteError
        output.write_text(encoded, encoding="utf-8", newline="\n")


@m1203_app.command("construct")
def cli_construct(
    request: Annotated[pathlib.Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    try:
        payload = _read_json(request)
        typed = _SERVICE.validate_request(payload)
        result = construct_mechanistic_features(typed)
    except (ValueError, TypeError, ValidationError) as exc:
        raise _CliRequestError from exc
    typer.echo(result.model_dump_json(indent=2))


@m1203_app.command("verify")
def cli_verify(
    result: Annotated[pathlib.Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    try:
        payload = _read_json(result)
        checked = BiomarkerPanelMechanisticFeatureResult.model_validate(payload)
    except (ValueError, TypeError, ValidationError) as exc:
        raise _CliResultError from exc
    typer.echo(
        json.dumps(
            {"moduleId": "GLIO-PROTEOGEN-M12-03", "verified": True, "resultId": checked.result_id},
            sort_keys=True,
        )
    )


__all__ = ["app", "m1203_app"]

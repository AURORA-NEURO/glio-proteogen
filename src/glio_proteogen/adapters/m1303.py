"""Standalone FastAPI and Typer adapters for provisional M13-03."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated, Final, cast

import typer
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from glio_proteogen.adapters.limits import RequestSizeLimitMiddleware, read_bounded
from glio_proteogen.contracts.m13_03 import (
    M1303_MAX_CANONICAL_REQUEST_BYTES,
    M1303_MAX_CANONICAL_RESULT_BYTES,
    ProteotypeMechanisticFeatureResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c11_protein_native_subtype import (
    m13_03_mechanistic_feature_constructor as m1303,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m13_03.schema import ContractName

MechanisticFeatureAuthorizationError = m1303.MechanisticFeatureAuthorizationError
M1303Service = m1303.M1303Service
validate_json_request = m1303.validate_json_request
verify_mechanistic_feature_replay = m1303.verify_mechanistic_feature_replay

_SERVICE: Final = M1303Service()
_SCHEMA_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "feature-object",
        "feature",
        "lineage",
        "relation",
        "configuration",
        "diagnostic",
    }
)


def _error(status: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": error_type, "message": message}},
    )


def _validation_error(error: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "type": "contract_validation_failed",
                "details": sanitized_validation_errors(error),
            }
        },
    )


async def _read_strict_body(request: Request) -> tuple[bytes, object] | JSONResponse:
    payload = await request.body()
    try:
        decoded = strict_json_loads(payload, max_bytes=M1303_MAX_CANONICAL_REQUEST_BYTES)
    except StrictJsonError as error:
        return JSONResponse(status_code=400, content={"error": strict_json_error_detail(error)})
    return payload, decoded


app = FastAPI(title="GLIO-PROTEOGEN M13-03", version="0.1.0-provisional")
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=M1303_MAX_CANONICAL_REQUEST_BYTES,
    result_max_bytes=M1303_MAX_CANONICAL_RESULT_BYTES,
)


@app.get("/v1/m13-03/schema/{name}", response_model=None)
def export_schema(name: str) -> dict[str, object] | JSONResponse:
    if name not in _SCHEMA_NAMES:
        return _error(404, "unknown_schema", "requested contract schema is not available")
    return contract_json_schema(name)  # type: ignore[arg-type]


@app.post("/v1/modules/M13-03/features")
async def construct_features(request: Request) -> JSONResponse:
    raw = await _read_strict_body(request)
    if isinstance(raw, JSONResponse):
        return raw
    payload, decoded = raw
    try:
        typed = validate_json_request(decoded, payload)
        result = _SERVICE.execute(typed)
    except MechanisticFeatureAuthorizationError:
        return _error(403, "authorization_failed", "M13-03 controls were not accepted")
    except ValidationError as error:
        return _validation_error(error)
    except TypeError:
        return _error(
            422, "contract_validation_failed", "request does not match the declared contract"
        )
    return JSONResponse(content=result.model_dump(mode="json"))


@app.post("/v1/modules/M13-03/verify")
async def verify_result(request: Request) -> JSONResponse:
    raw = await _read_strict_body(request)
    if isinstance(raw, JSONResponse):
        return raw
    payload, _decoded = raw
    try:
        result = ProteotypeMechanisticFeatureResult.model_validate_json(payload)
        verified = verify_mechanistic_feature_replay(result)
    except ValidationError:
        return _error(
            422, "contract_validation_failed", "result does not match the declared contract"
        )
    except ValueError:
        return _error(409, "replay_verification_failed", "result replay verification failed")
    return JSONResponse(content={"verified": True, "result_digest": verified.result_digest})


m1303_app = typer.Typer(add_completion=False, no_args_is_help=True)


def _load_bytes(path: Path, max_bytes: int) -> bytes:
    return read_bounded(path, max_bytes)


def _write_new(path: Path, payload: bytes) -> None:
    if path.exists():
        raise typer.BadParameter("output already exists; refusing overwrite")  # noqa: TRY003
    path.write_bytes(payload)


@m1303_app.command("export-schema")
def export_schema_command(
    name: Annotated[str, typer.Argument(help="contract schema name")],
    output: Annotated[Path, typer.Option("--output", "-o", help="new JSON output path")],
) -> None:
    if name not in _SCHEMA_NAMES:
        raise typer.BadParameter("unknown M13-03 schema name")  # noqa: TRY003
    _write_new(output, canonical_json_bytes(contract_json_schema(cast("ContractName", name))))
    typer.echo(str(output))


@m1303_app.command("construct")
def construct_command(
    input_path: Annotated[Path, typer.Argument(help="strict JSON request path")],
    output: Annotated[Path, typer.Option("--output", "-o", help="new JSON output path")],
) -> None:
    payload = _load_bytes(input_path, M1303_MAX_CANONICAL_REQUEST_BYTES)
    try:
        decoded = strict_json_loads(payload, max_bytes=M1303_MAX_CANONICAL_REQUEST_BYTES)
        request_model = validate_json_request(decoded, payload)
        result = _SERVICE.execute(request_model)
    except (
        StrictJsonError,
        ValidationError,
        TypeError,
        MechanisticFeatureAuthorizationError,
    ) as error:
        raise typer.BadParameter("request rejected by the M13-03 contract") from error  # noqa: TRY003
    _write_new(output, canonical_json_bytes(result))
    typer.echo(str(output))


@m1303_app.command("verify")
def verify_command(
    input_path: Annotated[Path, typer.Argument(help="strict JSON result path")],
) -> None:
    payload = _load_bytes(input_path, M1303_MAX_CANONICAL_RESULT_BYTES)
    try:
        strict_json_loads(payload, max_bytes=M1303_MAX_CANONICAL_RESULT_BYTES)
        result = ProteotypeMechanisticFeatureResult.model_validate_json(payload)
        verified = verify_mechanistic_feature_replay(result)
    except (StrictJsonError, ValidationError, ValueError) as error:
        raise typer.BadParameter("result replay verification failed") from error  # noqa: TRY003
    typer.echo(json.dumps({"verified": True, "result_digest": verified.result_digest}))


__all__ = ["app", "m1303_app"]

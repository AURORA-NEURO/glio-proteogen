"""Standalone FastAPI and Typer adapters for provisional M11-07."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves Path at runtime.
from typing import Annotated, Final

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from glio_proteogen.contracts.m11_07 import (
    M1107_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateVariantPeptidePlausibilityRequest,
    VariantPeptidePlausibilityAdjudicationResult,
    contract_json_schema,
)
from glio_proteogen.kernel.models import FrozenModel
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_07_plausibility_adjudicator as m1107,
)

PlausibilityAuthorizationError = m1107.PlausibilityAuthorizationError
PlausibilityReplayError = m1107.PlausibilityReplayError
_validate_json_request = m1107._validate_json_request
M1107Plugin = m1107.M1107Plugin
M1107Service = m1107.M1107Service

_MAX_ERROR_BYTES: Final = 4096
_service = M1107Service()
_plugin = M1107Plugin(_service)


class _CliParameterError(typer.BadParameter):
    def __init__(self, code: str) -> None:
        messages = {
            "read": "input file cannot be read",
            "large": "input exceeds the M11-07 byte limit",
            "overwrite": "output already exists; refusing overwrite",
            "write": "output file cannot be written",
            "request": "request does not match M11-07 contract",
            "replay": "replay verification failed",
        }
        super().__init__(messages[code])


class VerifyPayload(FrozenModel):
    """Strict envelope for replay verification."""

    request: AdjudicateVariantPeptidePlausibilityRequest
    result: VariantPeptidePlausibilityAdjudicationResult


app = FastAPI(title="GLIO-PROTEOGEN M11-07", version="0.1.0-provisional")
m1107_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


@app.exception_handler(StrictJsonError)
async def _strict_json_error(_request: Request, error: StrictJsonError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": strict_json_error_detail(error)})


@app.get("/v1/modules/M11-07/schema/{name}")
def export_schema(name: str) -> dict[str, object]:
    if name not in {"request", "output", "control", "evaluation", "conflict", "finding"}:
        raise HTTPException(status_code=404, detail="unknown M11-07 schema")
    return contract_json_schema(name)  # type: ignore[arg-type]


@app.post("/v1/modules/M11-07/plausibility")
async def adjudicate(request: Request) -> JSONResponse:
    body = await request.body()
    if len(body) > M1107_MAX_CANONICAL_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="request exceeds M11-07 byte limit")
    try:
        decoded = strict_json_loads(body, max_bytes=M1107_MAX_CANONICAL_REQUEST_BYTES)
        typed = _validate_json_request(decoded, body)
        result = _service.execute(typed)
    except StrictJsonError:
        raise
    except PlausibilityAuthorizationError as error:
        raise HTTPException(status_code=403, detail="upstream controls are not accepted") from error
    except ValidationError as error:
        return JSONResponse(
            status_code=422,
            content={"detail": sanitized_validation_errors(error)},
        )
    except (PlausibilityReplayError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422, detail="request does not match M11-07 contract"
        ) from error
    return JSONResponse(content=result.model_dump(mode="json"))


@app.post("/v1/modules/M11-07/verify")
async def verify(request: Request) -> JSONResponse:
    body = await request.body()
    if len(body) > M1107_MAX_CANONICAL_REQUEST_BYTES * 2:
        raise HTTPException(status_code=413, detail="verification envelope exceeds byte limit")
    try:
        decoded = strict_json_loads(body, max_bytes=M1107_MAX_CANONICAL_REQUEST_BYTES * 2)
        if not isinstance(decoded, dict):
            raise HTTPException(status_code=422, detail="verification envelope must be an object")
        request_value = decoded.get("request")
        if not isinstance(request_value, dict):
            raise HTTPException(status_code=422, detail="verification request must be an object")
        _validate_json_request(request_value, json.dumps(request_value, separators=(",", ":")))
        envelope = VerifyPayload.model_validate_json(body)
        result = _service.verify(envelope.request, envelope.result)
    except PlausibilityAuthorizationError as error:
        raise HTTPException(status_code=403, detail="upstream controls are not accepted") from error
    except ValidationError as error:
        return JSONResponse(
            status_code=422,
            content={"detail": sanitized_validation_errors(error)},
        )
    except (PlausibilityReplayError, TypeError, ValueError) as error:
        raise HTTPException(status_code=409, detail="replay verification failed") from error
    return JSONResponse(content={"verified": True, "result_digest": result.result_digest})


def _read_json(path: Path) -> bytes:
    try:
        body = path.read_bytes()
    except OSError as error:
        raise _CliParameterError("read") from error
    if len(body) > M1107_MAX_CANONICAL_REQUEST_BYTES:
        raise _CliParameterError("large")
    return body


def _write_json(path: Path, value: object) -> None:
    if path.exists():
        raise _CliParameterError("overwrite")
    try:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise _CliParameterError("write") from error


@m1107_app.command("export-schema")
def cli_export_schema(
    name: Annotated[
        str, typer.Argument(help="request, output, control, evaluation, conflict, or finding")
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M11-07 JSON Schema."""

    try:
        schema = export_schema(name)
    except HTTPException as error:
        raise typer.BadParameter(str(error.detail)) from error
    if output is None:
        typer.echo(json.dumps(schema, ensure_ascii=False, indent=2))
    else:
        _write_json(output, schema)


@m1107_app.command("adjudicate")
def cli_adjudicate(
    input_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Adjudicate one strict M11-07 JSON request."""

    body = _read_json(input_path)
    try:
        result = _plugin.run(_plugin.validate(body))
    except (PlausibilityAuthorizationError, ValidationError, ValueError, TypeError) as error:
        raise _CliParameterError("request") from error
    document = result.model_dump(mode="json")
    if output is None:
        typer.echo(json.dumps(document, ensure_ascii=False, indent=2))
    else:
        _write_json(output, document)


@m1107_app.command("verify")
def cli_verify(
    request_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    result_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    """Verify deterministic replay of a request and result pair."""

    request_body = _read_json(request_path)
    result_body = _read_json(result_path)
    try:
        request = _plugin.validate(request_body).request
        result = VariantPeptidePlausibilityAdjudicationResult.model_validate_json(result_body)
        _service.verify(request, result)
    except (PlausibilityAuthorizationError, ValidationError, ValueError, TypeError) as error:
        raise _CliParameterError("replay") from error
    typer.echo(json.dumps({"verified": True, "result_digest": result.result_digest}))


__all__ = ["VerifyPayload", "app", "m1107_app"]

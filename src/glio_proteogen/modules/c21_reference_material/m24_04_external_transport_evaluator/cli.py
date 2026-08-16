"""Typer adapter for provisional M24-04 transport evaluation."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m24_04 import (
    M2404_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelExternalTransportResult,
    EvaluateBiomarkerPanelExternalTransportRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2404AuthorizationError
from .service import M2404Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2404Service()
_REQUEST_ADAPTER = TypeAdapter(EvaluateBiomarkerPanelExternalTransportRequest)
_RESULT_ADAPTER = TypeAdapter(BiomarkerPanelExternalTransportResult)


class M2404CliError(typer.BadParameter):
    """Sanitized CLI boundary error."""


def _read_request(path: Path) -> EvaluateBiomarkerPanelExternalTransportRequest:
    try:
        data = path.read_bytes()
        strict_json_loads(data, max_bytes=M2404_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2404CliError("input does not satisfy the M24-04 contract") from error  # noqa: TRY003


def _read_result(path: Path) -> BiomarkerPanelExternalTransportResult:
    try:
        return _RESULT_ADAPTER.validate_json(path.read_bytes(), strict=True)
    except (OSError, ValueError, ValidationError) as error:
        raise M2404CliError("input is not a valid M24-04 result") from error  # noqa: TRY003


def _write(path: Path, payload: object) -> None:
    if path.exists():
        raise M2404CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.write_bytes(canonical_json_bytes(payload))


@app.command("export-schema")
def export_schema(
    name: str,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Export one strict M24-04 JSON schema."""

    try:
        schema = contract_json_schema(name)  # type: ignore[arg-type]
    except KeyError as error:
        raise M2404CliError("unknown M24-04 contract") from error  # noqa: TRY003
    if output is None:
        typer.echo(json.dumps(schema, sort_keys=True))
    else:
        _write(output, schema)


@app.command("validate")
def validate(path: Path) -> None:
    """Validate one request without evaluating it."""

    try:
        request = _read_request(path)
        _SERVICE.validate_request(request)
    except (M2404CliError, M2404AuthorizationError, ValidationError, ValueError) as error:
        raise M2404CliError("request was rejected by the M24-04 service") from error  # noqa: TRY003
    typer.echo(json.dumps({"request_id": request.request_id}, sort_keys=True))


@app.command("evaluate")
def evaluate(path: Path, output: Annotated[Path | None, typer.Option("--output")] = None) -> None:
    """Evaluate one request and optionally write its immutable result."""

    request = _read_request(path)
    try:
        result = _SERVICE.generate(request)
    except (M2404AuthorizationError, ValidationError, ValueError) as error:
        raise M2404CliError("request was rejected by the M24-04 service") from error  # noqa: TRY003
    if output is None:
        typer.echo(result.model_dump_json())
    else:
        _write(output, result.model_dump(mode="json"))
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Path) -> None:
    """Replay-verify one M24-04 result."""

    result = _read_result(path)
    try:
        replay = _SERVICE.replay(result)
    except (ValidationError, ValueError) as error:
        raise M2404CliError("result replay is invalid") from error  # noqa: TRY003
    if replay.result_digest != result.result_digest:
        raise M2404CliError("result replay is invalid")  # noqa: TRY003
    typer.echo(
        json.dumps({"verified": replay.result_digest == result.result_digest}, sort_keys=True)
    )


cli_app = app

__all__ = ["app", "cli_app"]

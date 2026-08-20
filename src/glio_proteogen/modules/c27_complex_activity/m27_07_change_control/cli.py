"""Typer commands for M27-07 change control."""

# ruff: noqa: TRY003, TRY004, TRY301, TC003

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, cast

import typer

from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.contracts.m27_07 import (
    M2707_MAX_CANONICAL_REQUEST_BYTES,
    M2707_MAX_CANONICAL_RESULT_BYTES,
    ComplexActivityChangeControlResult,
    ContractName,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control.service import M2707Service

cli = typer.Typer(add_completion=False, no_args_is_help=True)
_service = M2707Service()


def _read(path: Path, *, max_bytes: int) -> bytes:
    try:
        return read_bounded(path, max_bytes)
    except (OSError, RequestBodyTooLargeError) as error:
        raise typer.BadParameter("unable to read request") from error


def _write(path: Path | None, payload: object) -> None:
    encoded = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if path is None:
        typer.echo(encoded, nl=False)
        return
    if path.exists():
        raise typer.BadParameter("output already exists")
    try:
        path.write_text(encoded, encoding="utf-8", newline="\n")
    except OSError as error:
        raise typer.BadParameter("unable to write output") from error


@cli.command("export-schema")
def export_schema(name: Annotated[str, typer.Argument()]) -> None:
    """Export one strict M27-07 schema."""

    try:
        _write(None, contract_json_schema(cast("ContractName", name)))
    except KeyError as error:
        raise typer.BadParameter("unknown schema") from error


@cli.command("validate")
def validate(request: Annotated[Path, typer.Argument()]) -> None:
    """Validate a request without executing it."""

    try:
        parsed = _service.validate_request(
            _read(request, max_bytes=M2707_MAX_CANONICAL_REQUEST_BYTES)
        )
    except ValueError as error:
        raise typer.BadParameter("request validation failed") from error
    typer.echo(json.dumps(parsed.model_dump(mode="json"), sort_keys=True))


@cli.command("control")
def control(
    request: Annotated[Path, typer.Argument()],
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Execute change control and optionally write a result."""

    try:
        result = _service.execute_json(_read(request, max_bytes=M2707_MAX_CANONICAL_REQUEST_BYTES))
    except ValueError as error:
        raise typer.BadParameter("change control denied or invalid") from error
    _write(output, result.model_dump(mode="json"))


@cli.command("verify")
def verify(result: Annotated[Path, typer.Argument()]) -> None:
    """Verify a result digest and report JSON."""

    try:
        raw = _read(result, max_bytes=M2707_MAX_CANONICAL_RESULT_BYTES)
        value = strict_json_loads(raw, max_bytes=M2707_MAX_CANONICAL_RESULT_BYTES)
        if not isinstance(value, dict):
            raise ValueError("result must be a JSON object")
        parsed = ComplexActivityChangeControlResult.model_validate_json(
            canonical_json_bytes(value), strict=True
        )
    except (ValueError, TypeError) as error:
        raise typer.BadParameter("result verification failed") from error
    typer.echo(json.dumps({"verified": _service.verify(parsed)}, sort_keys=True))


__all__ = ["cli"]

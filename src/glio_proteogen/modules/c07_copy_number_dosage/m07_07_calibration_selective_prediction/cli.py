"""Typer CLI for strict M07-07 validation, calibration, and schema export."""

from __future__ import annotations

import json
import sys
from pathlib import Path  # noqa: TC003 - Typer resolves the runtime annotation.
from typing import Annotated

import typer
from pydantic import ValidationError

from glio_proteogen.contracts.m07_07 import (
    M0707_MAX_CANONICAL_REQUEST_BYTES,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import CalibrationAuthorizationError, CalibrationInputError
from .service import M0707Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _read(path: Path | None) -> object:
    raw = sys.stdin.buffer.read() if path is None else path.read_bytes()
    return strict_json_loads(raw, max_bytes=M0707_MAX_CANONICAL_REQUEST_BYTES)


def _write(payload: object, output: Path | None) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output is None:
        typer.echo(encoded, nl=False)
        return
    if output.exists():
        raise typer.BadParameter("output exists; refusing to overwrite")  # noqa: TRY003
    output.write_text(encoded, encoding="utf-8", newline="\n")


@app.command("export-schema")
def export_schema(
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export all provisional M07-07 JSON Schemas."""

    _write(contract_json_schemas(), output)


@app.command("validate")
def validate(
    input_path: Annotated[Path | None, typer.Option("--input", "-i")] = None,
) -> None:
    """Strictly validate a request and emit its canonical digest."""

    try:
        typed = M0707Service.validate_request(_read(input_path))
    except (CalibrationAuthorizationError, CalibrationInputError, ValidationError) as exc:
        raise typer.BadParameter("request rejected by strict M07-07 validation") from exc  # noqa: TRY003
    _write(
        {
            "module_id": "GLIO-PROTEOGEN-M07-07",
            "contract_version": typed.contract_version,
            "request_digest": canonical_request_digest(typed),
            "valid": True,
        },
        None,
    )


@app.command("calibrate")
def calibrate(
    input_path: Annotated[Path | None, typer.Option("--input", "-i")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Run deterministic selective calibration and emit the result."""

    try:
        result = M0707Service().execute(_read(input_path))
    except (CalibrationAuthorizationError, CalibrationInputError, ValidationError) as exc:
        raise typer.BadParameter("request rejected by strict M07-07 execution") from exc  # noqa: TRY003
    _write(result.model_dump(mode="json"), output)


if __name__ == "__main__":
    app()


__all__ = ["app"]

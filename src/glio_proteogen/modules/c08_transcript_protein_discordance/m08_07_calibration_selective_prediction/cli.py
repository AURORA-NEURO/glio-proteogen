"""Typer commands matching the M08-07 FastAPI validation boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from glio_proteogen.contracts.m08_07 import contract_json_schema, contract_json_schemas
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)

from .service import M0807Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _emit(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _load(path: Path) -> object:
    try:
        return strict_json_loads(path.read_bytes())
    except (OSError, StrictJsonError) as error:
        raise typer.BadParameter("input is not a valid bounded JSON document") from error


@app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="Contract name, or 'all'.")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict schema without overwriting an existing file."""

    try:
        value: object = contract_json_schemas() if name == "all" else contract_json_schema(name)  # type: ignore[arg-type]
    except (KeyError, ValueError) as error:
        raise typer.BadParameter("unknown contract name") from error
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output is None:
        typer.echo(encoded, nl=False)
        return
    if output.exists():
        raise typer.BadParameter("refusing to overwrite an existing output")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8", newline="\n")
    except OSError as error:
        raise typer.BadParameter("cannot write output") from error


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    """Strictly validate one request document and emit its canonical form."""

    try:
        request = M0807Service.validate_request(_load(path))
    except ValidationError as error:
        _emit({"valid": False, "errors": sanitized_validation_errors(error)})
        raise typer.Exit(code=2) from error
    _emit({"valid": True, "request": request.model_dump(mode="json")})


@app.command("calibrate")
def calibrate(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    """Execute the deterministic quality-gated calibration operation."""

    try:
        result = M0807Service().execute(_load(path))
    except ValidationError as error:
        _emit({"valid": False, "errors": sanitized_validation_errors(error)})
        raise typer.Exit(code=2) from error
    _emit(result.model_dump(mode="json"))


if __name__ == "__main__":  # pragma: no cover
    app()


__all__ = ["app"]


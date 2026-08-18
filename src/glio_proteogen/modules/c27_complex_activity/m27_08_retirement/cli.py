"""Typer CLI for M27-08 retirement and archive verification."""

# CLI errors are deliberately sanitized at the command boundary.
# ruff: noqa: TRY003, B904

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

if __package__ in {None, ""}:
    _SOURCE_ROOT = Path(__file__).resolve().parents[4]
    if str(_SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SOURCE_ROOT))

from glio_proteogen.contracts.m27_08 import (
    ComplexActivityRetirementResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement.service import M2708Service

cli = typer.Typer(help="M27-08 retirement and archival controls")


@cli.command("export-schema")
def export_schema(name: str, output: Path | None = None) -> None:
    """Export a named M27-08 schema without overwriting an existing file."""
    if name not in contract_json_schemas():
        raise typer.BadParameter("unknown schema")
    value = json.dumps(contract_json_schema(name), indent=2, sort_keys=True)
    if output is None:
        typer.echo(value)
        return
    if output.exists():
        raise typer.BadParameter("output already exists")
    output.write_text(value + "\n", encoding="utf-8")


@cli.command("validate")
def validate(request: Path) -> None:
    try:
        parsed = M2708Service().validate_request(request.read_bytes())
    except ValueError as error:
        raise typer.BadParameter("request validation failed") from error
    typer.echo(parsed.model_dump_json())


@cli.command("retire")
def retire(request: Path, output: Path | None = None) -> None:
    try:
        result = M2708Service().execute_json(request.read_bytes())
    except ValueError as error:
        raise typer.BadParameter("retirement denied or invalid") from error
    payload = result.model_dump_json()
    if output is not None:
        if output.exists():
            raise typer.BadParameter("output already exists")
        output.write_text(payload + "\n", encoding="utf-8")
    else:
        typer.echo(payload)


@cli.command("verify")
def verify(result: Path) -> None:
    try:
        parsed = ComplexActivityRetirementResult.model_validate_json(
            result.read_bytes(), strict=True
        )
        verified = M2708Service().verify(parsed)
    except ValueError:
        typer.echo(json.dumps({"verified": False}))
        raise typer.Exit(code=1)
    typer.echo(json.dumps({"verified": verified}))
    if not verified:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    cli()

__all__ = ["cli"]

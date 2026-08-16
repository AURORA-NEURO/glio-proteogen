"""Typer CLI for strict M09-03 validation and estimation."""

# CLI diagnostics intentionally collapse internal exceptions into stable messages.
# ruff: noqa: TRY003, TRY300, TC003

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Final

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_03 import (
    M0903_MAX_CANONICAL_REQUEST_BYTES,
    EstimateComplexActivityBaselineRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M0903AuthorizationError
from .service import M0903Service

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateComplexActivityBaselineRequest)
_CONTRACT_NAMES: Final = frozenset({"request", "output", "configuration", "estimate", "diagnostic"})
app = typer.Typer(help="M09-03 complex-activity mature baseline estimator.")


def _read(path: Path) -> bytes:
    try:
        body = path.read_bytes()
        strict_json_loads(body, max_bytes=M0903_MAX_CANONICAL_REQUEST_BYTES)
        return body
    except (OSError, StrictJsonError) as error:
        raise typer.BadParameter("request is not bounded strict JSON") from error


def _request_from_file(path: Path) -> EstimateComplexActivityBaselineRequest:
    try:
        return _REQUEST_ADAPTER.validate_json(_read(path), strict=True)
    except ValidationError as error:
        raise typer.BadParameter("request does not match the M09-03 contract") from error


@app.command("export-schema")
def export_schema(contract: Annotated[str, typer.Argument(help="M09-03 contract name.")]) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    if contract not in _CONTRACT_NAMES:
        raise typer.BadParameter("unknown M09-03 contract")
    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))  # type: ignore[arg-type]


@app.command("validate")
def validate(request: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Parse and validate one request before emitting canonical JSON."""

    typed = M0903Service().validate_request(_request_from_file(request))
    typer.echo(canonical_json_bytes(typed.model_dump(mode="json")).decode("utf-8"))


@app.command("estimate")
def estimate(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option(help="Optional new canonical result path.")] = None,
) -> None:
    """Estimate one baseline; abstention exits nonzero after writing its result."""

    try:
        built = M0903Service().construct(_request_from_file(request))
    except (
        M0903AuthorizationError,
        ValidationError,
        ValueError,
        TypeError,
        StrictJsonError,
    ) as error:
        raise typer.BadParameter("M09-03 estimation input is invalid") from error
    if output is not None and output.exists():
        raise typer.BadParameter("output already exists")
    if output is None:
        typer.echo(built.canonical_bytes.decode("utf-8"))
    else:
        output.write_bytes(built.canonical_bytes)
    if built.result.status.value != "estimated":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()


__all__ = ["app"]

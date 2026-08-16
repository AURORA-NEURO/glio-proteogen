"""Typer CLI for strict M09-02 validation and construction."""

# CLI diagnostics intentionally collapse internal exceptions into stable messages.
# ruff: noqa: TRY003, TRY300, TC003

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Final

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_02 import (
    M0902_MAX_CANONICAL_REQUEST_BYTES,
    ConstructComplexActivityRepresentationRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M0902AuthorizationError
from .service import M0902Service

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructComplexActivityRepresentationRequest)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "feature-specification",
        "feature-lineage",
        "representation-feature",
        "transformation",
        "policy",
        "leakage-check",
    }
)
app = typer.Typer(help="M09-02 complex-activity representation constructor.")


def _read(path: Path) -> bytes:
    try:
        body = path.read_bytes()
        strict_json_loads(body, max_bytes=M0902_MAX_CANONICAL_REQUEST_BYTES)
        return body
    except (OSError, StrictJsonError) as error:
        raise typer.BadParameter("request is not bounded strict JSON") from error


def _request_from_file(path: Path) -> ConstructComplexActivityRepresentationRequest:
    try:
        return _REQUEST_ADAPTER.validate_json(_read(path), strict=True)
    except ValidationError as error:
        raise typer.BadParameter("request does not match the M09-02 contract") from error


@app.command("export-schema")
def export_schema(contract: Annotated[str, typer.Argument(help="M09-02 contract name.")]) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    if contract not in _CONTRACT_NAMES:
        raise typer.BadParameter("unknown M09-02 contract")
    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))  # type: ignore[arg-type]


@app.command("validate")
def validate(request: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Parse and validate one request before emitting canonical JSON."""

    typed = M0902Service().validate_request(_request_from_file(request))
    typer.echo(canonical_json_bytes(typed.model_dump(mode="json")).decode("utf-8"))


@app.command("construct")
def construct(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option(help="Optional new canonical result path.")] = None,
) -> None:
    """Construct one result; abstention exits nonzero after writing the result."""

    try:
        built = M0902Service().construct(_request_from_file(request))
    except (
        M0902AuthorizationError,
        ValidationError,
        ValueError,
        TypeError,
        StrictJsonError,
    ) as error:
        raise typer.BadParameter("M09-02 construction input is invalid") from error
    if output is not None and output.exists():
        raise typer.BadParameter("output already exists")
    if output is None:
        typer.echo(built.canonical_bytes.decode("utf-8"))
    else:
        output.write_bytes(built.canonical_bytes)
    if built.result.status.value != "constructed":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()


__all__ = ["app"]

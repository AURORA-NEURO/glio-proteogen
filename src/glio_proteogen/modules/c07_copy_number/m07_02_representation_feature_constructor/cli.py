"""Typer CLI for strict M07-02 validation and construction."""

# CLI diagnostics intentionally collapse internal exceptions into stable messages.
# ruff: noqa: TRY003, TRY300, TC003

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Final

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m07_02 import (
    M0702_MAX_CANONICAL_REQUEST_BYTES,
    ConstructProteotypeAnalysisRepresentationRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .service import M0702Service

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructProteotypeAnalysisRepresentationRequest)
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
app = typer.Typer(help="M07-02 representation and feature constructor.")


def _read(path: Path) -> bytes:
    try:
        body = path.read_bytes()
        strict_json_loads(body, max_bytes=M0702_MAX_CANONICAL_REQUEST_BYTES)
        return body
    except (OSError, StrictJsonError) as error:
        raise typer.BadParameter("request is not bounded strict JSON") from error


def _request_from_file(path: Path) -> ConstructProteotypeAnalysisRepresentationRequest:
    body = _read(path)
    try:
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except ValidationError as error:
        raise typer.BadParameter("request does not match the M07-02 contract") from error


@app.command("export-schema")
def export_schema(
    contract: Annotated[str, typer.Argument(help="M07-02 contract name.")],
) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    if contract not in _CONTRACT_NAMES:
        raise typer.BadParameter("unknown M07-02 contract")
    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))  # type: ignore[arg-type]


@app.command("validate")
def validate(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Parse and validate one request before emitting canonical JSON."""

    typed = _request_from_file(request)
    typer.echo(canonical_json_bytes(typed.model_dump(mode="json")).decode("utf-8"))


@app.command("construct")
def construct(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option(help="Optional new canonical result path.")] = None,
) -> None:
    """Construct one representation; abstention exits nonzero after writing the result."""

    try:
        built = M0702Service().construct(_request_from_file(request))
    except (ValidationError, ValueError, TypeError, StrictJsonError) as error:
        raise typer.BadParameter("M07-02 construction input is invalid") from error
    encoded = built.canonical_bytes
    if output is None:
        typer.echo(encoded.decode("utf-8"))
    else:
        if output.exists():
            raise typer.BadParameter("output already exists")
        output.write_bytes(encoded)
    if built.result.status.value != "constructed":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()


__all__ = ["app"]

"""Typer CLI for strict M06-05 validation and integration."""

# CLI diagnostics intentionally collapse internal exceptions into stable messages.
# ruff: noqa: TRY003, TRY300

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Final

import typer
from pydantic import TypeAdapter, ValidationError

if __package__ in {None, ""}:
    _SOURCE_ROOT = Path(__file__).resolve().parents[4]
    if str(_SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SOURCE_ROOT))

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m06_05 import (
    M0605_MAX_CANONICAL_REQUEST_BYTES,
    IntegrateProteinAbundanceConstraintsRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c06_protein_abundance.m06_05_mechanism_constraint_integrator.service import (  # noqa: E501
    M0605Service,
)

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateProteinAbundanceConstraintsRequest)
_CONTRACT_NAMES: Final = frozenset(
    {"request", "output", "constraint", "constraint-set", "evaluation", "ablation", "estimate"}
)
app = typer.Typer(help="M06-05 mechanism and constraint integrator.")


def _read(path: Path) -> bytes:
    try:
        body = read_bounded(path, max_bytes=M0605_MAX_CANONICAL_REQUEST_BYTES)
        strict_json_loads(body, max_bytes=M0605_MAX_CANONICAL_REQUEST_BYTES)
        return body
    except (OSError, StrictJsonError) as error:
        raise typer.BadParameter("request is not bounded strict JSON") from error


def _request_from_file(path: Path) -> IntegrateProteinAbundanceConstraintsRequest:
    body = _read(path)
    try:
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except ValidationError as error:
        raise typer.BadParameter("request does not match the M06-05 contract") from error


@app.command("export-schema")
def export_schema(
    contract: Annotated[str, typer.Argument(help="M06-05 contract name.")],
) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    if contract not in _CONTRACT_NAMES:
        raise typer.BadParameter("unknown M06-05 contract")
    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))  # type: ignore[arg-type]


@app.command("validate")
def validate(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Parse and validate one request before emitting canonical JSON."""

    typed = _request_from_file(request)
    typer.echo(canonical_json_bytes(typed.model_dump(mode="json")).decode("utf-8"))


@app.command("integrate")
def integrate(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option(help="Optional new canonical result path.")] = None,
) -> None:
    """Integrate one request; abstention exits nonzero after writing the result."""

    try:
        built = M0605Service().integrate(_request_from_file(request))
    except (ValidationError, ValueError, TypeError, StrictJsonError) as error:
        raise typer.BadParameter("M06-05 integration input is invalid") from error
    encoded = built.canonical_bytes
    if output is None:
        typer.echo(encoded.decode("utf-8"))
    else:
        if output.exists():
            raise typer.BadParameter("output already exists")
        output.write_bytes(encoded)
    if built.result.status.value != "integrated":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()


__all__ = ["app"]

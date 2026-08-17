"""Typer CLI for strict M07-01 formal-state validation."""

# CLI errors intentionally collapse internal details into stable diagnostics.
# ruff: noqa: TRY003

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

from glio_proteogen.contracts.m07_01 import (
    M0701_MAX_CANONICAL_REQUEST_BYTES,
    ValidateCopyNumberStateRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c07_copy_number.m07_01_formal_state_feature_schema.service import (
    M0701Service,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateCopyNumberStateRequest)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "schema",
        "feature-definition",
        "feature-value",
        "invariant",
        "invariant-result",
        "migration",
    }
)
app = typer.Typer(help="M07-01 formal state and feature schema.")


def _request_from_file(path: Path) -> ValidateCopyNumberStateRequest:
    try:
        payload = path.read_bytes()
        strict_json_loads(payload, max_bytes=M0701_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(payload, strict=True)
    except (OSError, StrictJsonError, ValidationError) as error:
        raise typer.BadParameter("request does not match the M07-01 contract") from error


@app.command("export-schema")
def export_schema(contract: Annotated[str, typer.Argument(help="M07-01 contract name.")]) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    if contract not in _CONTRACT_NAMES:
        raise typer.BadParameter("unknown M07-01 contract")
    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))  # type: ignore[arg-type]


@app.command("validate")
def validate(request: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate and emit the canonical request document."""

    typed = _request_from_file(request)
    typer.echo(canonical_json_bytes(typed.model_dump(mode="json")).decode("utf-8"))


@app.command("execute")
def execute(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option(help="Optional new result path.")] = None,
) -> None:
    """Execute validation; an abstention exits nonzero after writing its result."""

    try:
        built = M0701Service().execute(_request_from_file(request))
    except (ValidationError, ValueError, TypeError, StrictJsonError) as error:
        raise typer.BadParameter("M07-01 execution input is invalid") from error
    encoded = built.canonical_bytes
    if output is None:
        typer.echo(encoded.decode("utf-8"))
    else:
        if output.exists():
            raise typer.BadParameter("output already exists")
        output.write_bytes(encoded)
    if built.result.status.value != "valid":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()


__all__ = ["app"]

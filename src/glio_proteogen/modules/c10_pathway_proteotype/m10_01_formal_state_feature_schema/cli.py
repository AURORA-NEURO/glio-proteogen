"""Typer CLI for strict M10-01 validation and execution."""

# CLI diagnostics intentionally collapse internal details into stable messages.
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

from glio_proteogen.contracts.m10_01 import (
    M1001_MAX_CANONICAL_REQUEST_BYTES,
    ProteinRnaValidationStatus,
    ValidateProteinRnaDiscordanceStateRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema.engine import (  # noqa: E501
    M1001AuthorizationError,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_01_formal_state_feature_schema.service import (  # noqa: E501
    M1001Service,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateProteinRnaDiscordanceStateRequest)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "feature-definition",
        "feature-value",
        "invariant",
        "invariant-result",
        "schema",
        "migration",
        "verification",
    }
)
app = typer.Typer(help="M10-01 formal state and feature schema.")


def _read(path: Path) -> bytes:
    try:
        body = path.read_bytes()
        strict_json_loads(body, max_bytes=M1001_MAX_CANONICAL_REQUEST_BYTES)
        return body
    except (OSError, StrictJsonError) as error:
        raise typer.BadParameter("request is not bounded strict JSON") from error


def _request_from_file(path: Path) -> ValidateProteinRnaDiscordanceStateRequest:
    body = _read(path)
    try:
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except ValidationError as error:
        raise typer.BadParameter("request does not match the M10-01 contract") from error


@app.command("export-schema")
def export_schema(
    contract: Annotated[str, typer.Argument(help="M10-01 contract name.")],
) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    if contract not in _CONTRACT_NAMES:
        raise typer.BadParameter("unknown M10-01 contract")
    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))  # type: ignore[arg-type]


@app.command("validate")
def validate(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Parse and validate one request before emitting canonical JSON."""

    typed = _request_from_file(request)
    M1001Service().validate_request(typed)
    typer.echo(canonical_json_bytes(typed.model_dump(mode="json")).decode("utf-8"))


@app.command("execute")
def execute(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option(help="Optional new canonical result path.")] = None,
) -> None:
    """Execute one request; invalid or abstained results exit nonzero."""

    try:
        built = M1001Service().execute(_request_from_file(request))
    except (
        M1001AuthorizationError,
        ValidationError,
        ValueError,
        TypeError,
        StrictJsonError,
    ) as error:
        raise typer.BadParameter("M10-01 execution input is invalid") from error
    encoded = built.canonical_bytes
    if output is None:
        typer.echo(encoded.decode("utf-8"))
    else:
        if output.exists():
            raise typer.BadParameter("output already exists")
        output.write_bytes(encoded)
    if built.result.status is not ProteinRnaValidationStatus.VALID:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()


__all__ = ["app"]

"""Typer CLI for strict M09-01 formal-state validation and replay verification."""

# CLI diagnostics intentionally collapse internal exceptions into stable messages.
# ruff: noqa: TRY003, TRY300, TC003

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Final

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_01 import (
    M0901_MAX_CANONICAL_REQUEST_BYTES,
    M0901_MAX_CANONICAL_RESULT_BYTES,
    ValidateComplexActivityStateRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M0901AuthorizationError, M0901FormalStateEngine
from .service import M0901Service

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateComplexActivityStateRequest)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "feature-definition",
        "feature-value",
        "invariant",
        "invariant-result",
        "constraint",
        "compatibility",
        "schema",
        "migration",
    }
)
app = typer.Typer(help="M09-01 formal complex-activity state validator.")


def _result_document(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise TypeError("result is not an object")
    return payload


def _read(path: Path, *, max_bytes: int) -> bytes:
    try:
        body = path.read_bytes()
        strict_json_loads(body, max_bytes=max_bytes)
        return body
    except (OSError, StrictJsonError) as error:
        raise typer.BadParameter("request is not bounded strict JSON") from error


def _request_from_file(path: Path) -> ValidateComplexActivityStateRequest:
    body = _read(path, max_bytes=M0901_MAX_CANONICAL_REQUEST_BYTES)
    try:
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except ValidationError as error:
        raise typer.BadParameter("request does not match the M09-01 contract") from error


@app.command("export-schema")
def export_schema(contract: Annotated[str, typer.Argument(help="M09-01 contract name.")]) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    if contract not in _CONTRACT_NAMES:
        raise typer.BadParameter("unknown M09-01 contract")
    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))  # type: ignore[arg-type]


@app.command("validate")
def validate(request: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Parse and validate one request before emitting canonical JSON."""

    typed = _request_from_file(request)
    M0901Service().validate_request(typed)
    typer.echo(canonical_json_bytes(typed.model_dump(mode="json")).decode("utf-8"))


@app.command("execute")
def execute(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option(help="Optional new canonical result path.")] = None,
) -> None:
    """Validate one request and emit a canonical result; abstention exits nonzero."""

    try:
        built = M0901Service().execute(_request_from_file(request))
    except (
        M0901AuthorizationError,
        ValidationError,
        ValueError,
        TypeError,
        StrictJsonError,
    ) as error:
        raise typer.BadParameter("M09-01 execution input is invalid") from error
    encoded = built.canonical_bytes
    if output is None:
        typer.echo(encoded.decode("utf-8"))
    else:
        if output.exists():
            raise typer.BadParameter("output already exists")
        output.write_bytes(encoded)
    if built.result.status.value != "valid":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(
    result: Annotated[Path, typer.Argument(exists=True, readable=True)],
    canonical: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Verify result and canonical bytes, returning nonzero on tamper or mismatch."""

    try:
        result_body = _read(result, max_bytes=M0901_MAX_CANONICAL_RESULT_BYTES)
        canonical_body = canonical.read_bytes()
        decoded = strict_json_loads(result_body, max_bytes=M0901_MAX_CANONICAL_RESULT_BYTES)
        outcome = M0901FormalStateEngine.verify(_result_document(decoded), canonical_body)
    except (OSError, StrictJsonError, TypeError, ValueError) as error:
        raise typer.BadParameter("M09-01 replay input is invalid") from error
    typer.echo(json.dumps({"verified": outcome.verified, "reason": outcome.reason}))
    if not outcome.verified:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

__all__ = ["app"]

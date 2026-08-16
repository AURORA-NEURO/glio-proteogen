"""Typer commands for strict M26-07 change-control operations."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime annotations.
from typing import Annotated, cast

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_07 import (
    M2607_MAX_CANONICAL_REQUEST_BYTES,
    ContractName,
    ControlProteinSubtypeChangeRequest,
    ProteinSubtypeChangeControlResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2607AuthorizationError
from .service import M2607ChangeControlService

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2607ChangeControlService()
_REQUEST_ADAPTER = TypeAdapter(ControlProteinSubtypeChangeRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypeChangeControlResult)
_CONTRACT_NAMES = frozenset(
    {
        "request",
        "output",
        "proposal",
        "revalidation",
        "comparison",
        "rollback",
        "package",
        "finding",
    }
)


class M2607CliError(typer.BadParameter):
    """Sanitized M26-07 command-line validation error."""


def _read_request(path: Path) -> ControlProteinSubtypeChangeRequest:
    try:
        data = path.read_bytes()
        strict_json_loads(data, max_bytes=M2607_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2607CliError(  # noqa: TRY003
            "input must satisfy the strict M26-07 request contract"
        ) from error


def _read_result(path: Path) -> ProteinSubtypeChangeControlResult:
    try:
        data = path.read_bytes()
        strict_json_loads(data, max_bytes=M2607_MAX_CANONICAL_REQUEST_BYTES)
        return _RESULT_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2607CliError("input must be a valid M26-07 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2607CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="name of an M26-07 contract schema")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M26-07 schema."""

    if name not in _CONTRACT_NAMES:
        raise M2607CliError("unknown M26-07 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(cast("ContractName", name)))
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate change-control material without promoting it."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2607AuthorizationError) as error:
        raise M2607CliError("request does not satisfy the M26-07 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("control")
def control(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Control one change and emit its canonical result."""

    try:
        result = _SERVICE.control(_read_request(path))
    except (ValidationError, ValueError, M2607AuthorizationError) as error:
        raise M2607CliError(  # noqa: TRY003
            "request was rejected by the M26-07 change-control boundary"
        ) from error
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify an M26-07 result by canonical replay."""

    result = _read_result(path)
    try:
        replay = _SERVICE.verify(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2607CliError("result replay is invalid") from error  # noqa: TRY003
    typer.echo(
        json.dumps({"verified": True, "result_digest": replay.result_digest}, sort_keys=True)
    )


__all__ = ["M2607CliError", "app"]

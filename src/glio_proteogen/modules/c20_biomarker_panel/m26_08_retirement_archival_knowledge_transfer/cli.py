"""Typer commands for strict M26-08 retirement operations."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime annotations.
from typing import Annotated, cast

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m26_08 import (
    M2608_MAX_CANONICAL_REQUEST_BYTES,
    M2608_MAX_CANONICAL_RESULT_BYTES,
    ContractName,
    ProteinSubtypeRetirementResult,
    RetireProteinSubtypeServiceRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2608AuthorizationError
from .service import M2608RetirementService

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2608RetirementService()
_REQUEST_ADAPTER = TypeAdapter(RetireProteinSubtypeServiceRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypeRetirementResult)
_CONTRACT_NAMES = frozenset(
    {
        "request",
        "output",
        "criterion",
        "migration",
        "evidence",
        "communication",
        "archive",
        "configuration",
        "package",
        "finding",
    }
)


class M2608CliError(typer.BadParameter):
    """Sanitized M26-08 command-line validation error."""


def _read_request(path: Path) -> RetireProteinSubtypeServiceRequest:
    try:
        data = read_bounded(path, M2608_MAX_CANONICAL_REQUEST_BYTES)
        strict_json_loads(data, max_bytes=M2608_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2608CliError(  # noqa: TRY003
            "input must satisfy the strict M26-08 request contract"
        ) from error


def _read_result(path: Path) -> ProteinSubtypeRetirementResult:
    try:
        data = read_bounded(path, M2608_MAX_CANONICAL_RESULT_BYTES)
        strict_json_loads(data, max_bytes=M2608_MAX_CANONICAL_RESULT_BYTES)
        return _RESULT_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2608CliError("input must be a valid M26-08 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2608CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="name of an M26-08 contract schema")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M26-08 schema."""

    if name not in _CONTRACT_NAMES:
        raise M2608CliError("unknown M26-08 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(cast("ContractName", name)))
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate retirement material without executing a retirement."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2608AuthorizationError) as error:
        raise M2608CliError("request does not satisfy the M26-08 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("retire")
def retire(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Retire one service and emit its canonical result."""

    try:
        result = _SERVICE.retire(_read_request(path))
    except (ValidationError, ValueError, M2608AuthorizationError) as error:
        raise M2608CliError(  # noqa: TRY003
            "request was rejected by the M26-08 retirement boundary"
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
    """Verify an M26-08 result by canonical replay."""

    result = _read_result(path)
    try:
        replay = _SERVICE.verify(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2608CliError("result replay is invalid") from error  # noqa: TRY003
    typer.echo(
        json.dumps({"verified": True, "result_digest": replay.result_digest}, sort_keys=True)
    )


__all__ = ["M2608CliError", "app"]

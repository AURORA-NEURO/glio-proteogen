"""Typer commands for strict M27-05 telemetry operations."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m27_05 import (
    M2705_MAX_CANONICAL_REQUEST_BYTES,
    M2705_MAX_CANONICAL_RESULT_BYTES,
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2705AuthorizationError
from .service import M2705Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2705Service()
_REQUEST_ADAPTER = TypeAdapter(EmitProteomicsTelemetryRequest)
_RESULT_ADAPTER = TypeAdapter(ProteomicsTelemetryResult)
_CONTRACT_NAMES = frozenset(
    {
        "request",
        "output",
        "stream",
        "sample",
        "dashboard",
        "alert",
        "reviewer-action",
        "safe-failure",
    }
)


class M2705CliError(typer.BadParameter):
    """Sanitized M27-05 command-line validation error."""


def _read_request(path: Path) -> EmitProteomicsTelemetryRequest:
    try:
        data = read_bounded(path, M2705_MAX_CANONICAL_REQUEST_BYTES)
        strict_json_loads(data, max_bytes=M2705_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2705CliError("input must satisfy the strict M27-05 request contract") from error  # noqa: TRY003


def _read_result(path: Path) -> ProteomicsTelemetryResult:
    try:
        data = read_bounded(path, M2705_MAX_CANONICAL_RESULT_BYTES)
        strict_json_loads(data, max_bytes=M2705_MAX_CANONICAL_RESULT_BYTES)
        return _RESULT_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2705CliError("input must be a valid M27-05 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2705CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="name of an M27-05 contract schema")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M27-05 schema."""

    if name not in _CONTRACT_NAMES:
        raise M2705CliError("unknown M27-05 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate telemetry request without emitting it."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2705AuthorizationError) as error:
        raise M2705CliError("request does not satisfy the M27-05 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("emit")
def emit(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Emit telemetry or safe abstention."""

    try:
        result = _SERVICE.emit(_read_request(path))
    except (ValidationError, ValueError, M2705AuthorizationError) as error:
        raise M2705CliError("request was rejected by the M27-05 telemetry service") from error  # noqa: TRY003
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify a telemetry result by canonical replay."""

    result = _read_result(path)
    try:
        replay = _SERVICE.replay(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2705CliError("result replay is invalid") from error  # noqa: TRY003
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["M2705CliError", "app"]

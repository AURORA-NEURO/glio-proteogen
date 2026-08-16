"""Typer commands for strict M26-05 observability emission and replay."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_05 import (
    M2605_MAX_CANONICAL_REQUEST_BYTES,
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2605AuthorizationError, M2605ReplayError
from .service import M2605ObservabilityService

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2605ObservabilityService()
_REQUEST_ADAPTER: TypeAdapter[EmitProteomicsTelemetryRequest] = TypeAdapter(
    EmitProteomicsTelemetryRequest
)
_RESULT_ADAPTER: TypeAdapter[ProteomicsTelemetryResult] = TypeAdapter(ProteomicsTelemetryResult)
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


class M2605CliError(typer.BadParameter):
    """Sanitized M26-05 command-line validation error."""


def _read_request(path: Path) -> EmitProteomicsTelemetryRequest:
    try:
        data = path.read_bytes()
        decoded = strict_json_loads(data, max_bytes=M2605_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2605CliError("input must satisfy the strict M26-05 request contract") from error  # noqa: TRY003


def _read_result(path: Path) -> ProteomicsTelemetryResult:
    try:
        data = path.read_bytes()
        decoded = strict_json_loads(data, max_bytes=M2605_MAX_CANONICAL_REQUEST_BYTES)
        return _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2605CliError("input must be a valid M26-05 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2605CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="name of an M26-05 contract schema")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M26-05 schema."""

    if name not in _CONTRACT_NAMES:
        raise M2605CliError("unknown M26-05 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate telemetry input without emitting a result."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2605AuthorizationError) as error:
        raise M2605CliError("request does not satisfy the M26-05 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("emit")
def emit(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Emit telemetry or return an explicit safe abstention."""

    try:
        result = _SERVICE.execute(_read_request(path))
    except (ValidationError, ValueError, M2605AuthorizationError) as error:
        raise M2605CliError("request was rejected by the M26-05 telemetry service") from error  # noqa: TRY003
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=3)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify one M26-05 result by canonical replay."""

    result = _read_result(path)
    try:
        replay = _SERVICE.verify(result)
    except (M2605ReplayError, TypeError, ValueError, ValidationError) as error:
        raise M2605CliError("result replay is invalid") from error  # noqa: TRY003
    typer.echo(
        json.dumps({"verified": True, "result_digest": replay.result_digest}, sort_keys=True)
    )


__all__ = ["M2605CliError", "app"]

"""Typer commands for strict M26-04 gateway operations."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_04 import (
    M2604_MAX_CANONICAL_REQUEST_BYTES,
    ProteinSubtypeAccessSurfaceResult,
    PublishProteinSubtypeAccessSurfaceRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2604AuthorizationError
from .service import M2604Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2604Service()
_REQUEST_ADAPTER = TypeAdapter(PublishProteinSubtypeAccessSurfaceRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypeAccessSurfaceResult)
_CONTRACT_NAMES = frozenset(
    {
        "request",
        "output",
        "operation",
        "authorization",
        "idempotency",
        "job",
        "compatibility",
        "error",
        "audit",
        "configuration",
        "surface",
        "finding",
    }
)


class M2604CliError(typer.BadParameter):
    """Sanitized M26-04 command-line validation error."""


def _read_request(path: Path) -> PublishProteinSubtypeAccessSurfaceRequest:
    try:
        data = path.read_bytes()
        strict_json_loads(data, max_bytes=M2604_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2604CliError(  # noqa: TRY003
            "input must satisfy the strict M26-04 request contract"
        ) from error


def _read_result(path: Path) -> ProteinSubtypeAccessSurfaceResult:
    try:
        data = path.read_bytes()
        strict_json_loads(data)
        return _RESULT_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2604CliError("input must be a valid M26-04 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2604CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="name of an M26-04 contract schema")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M26-04 schema."""

    if name not in _CONTRACT_NAMES:
        raise M2604CliError("unknown M26-04 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate gateway material without publishing it."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2604AuthorizationError) as error:
        raise M2604CliError(  # noqa: TRY003
            "request does not satisfy the M26-04 contract"
        ) from error
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("publish")
def publish(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Publish the typed API/SDK/CLI access surface."""

    try:
        result = _SERVICE.publish(_read_request(path))
    except (ValidationError, ValueError, M2604AuthorizationError) as error:
        raise M2604CliError("request was rejected by the M26-04 gateway") from error  # noqa: TRY003
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify an M26-04 result by canonical replay."""

    result = _read_result(path)
    try:
        replay = _SERVICE.replay(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2604CliError("result replay is invalid") from error  # noqa: TRY003
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["M2604CliError", "app"]

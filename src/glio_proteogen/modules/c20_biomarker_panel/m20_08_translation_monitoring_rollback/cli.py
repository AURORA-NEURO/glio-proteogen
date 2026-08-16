"""Typer adapter for provisional M20-08 translation monitoring."""

# ruff: noqa: TRY003

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m20_08 import (
    M2008_MAX_CANONICAL_REQUEST_BYTES,
    MonitorProteinSubtypeTranslationHealthRequest,
    ProteinSubtypeTranslationHealthResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2008AuthorizationError
from .service import M2008Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2008Service()
_REQUEST_ADAPTER = TypeAdapter(MonitorProteinSubtypeTranslationHealthRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypeTranslationHealthResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "report",
    "signal",
    "assessment",
    "rollback-plan",
    "configuration",
    "diagnostic",
}


class M2008CliError(typer.BadParameter):
    """Sanitized M20-08 command-line validation error."""


def _read_request(path: Path) -> MonitorProteinSubtypeTranslationHealthRequest:
    try:
        data = path.read_bytes()
        strict_json_loads(data, max_bytes=M2008_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2008CliError("input must satisfy the strict M20-08 request contract") from error


def _read_result(path: Path) -> ProteinSubtypeTranslationHealthResult:
    try:
        return _RESULT_ADAPTER.validate_json(path.read_bytes(), strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2008CliError("input must be a valid M20-08 result") from error


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2008CliError("output already exists; refusing to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[
        str,
        typer.Argument(
            help=(
                "request, output, report, signal, assessment, rollback-plan, configuration, "
                "or diagnostic"
            )
        ),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M20-08 contract schema."""

    if name not in _CONTRACT_NAMES:
        raise M2008CliError("unknown M20-08 contract")
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate one request without monitoring it."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2008AuthorizationError) as error:
        raise M2008CliError("request does not satisfy the M20-08 contract") from error
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("monitor")
def monitor(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Monitor one request and emit the canonical result."""

    try:
        result = _SERVICE.execute(_read_request(path))
    except (ValidationError, ValueError, M2008AuthorizationError) as error:
        raise M2008CliError("request was rejected by the M20-08 service") from error
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.health_status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify one immutable result by replaying its exact request."""

    result = _read_result(path)
    try:
        replay = _SERVICE.verify(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2008CliError("result replay is invalid") from error
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["app"]

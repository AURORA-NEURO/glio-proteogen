"""Typer commands for strict M27-06 security/access operations."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m27_06 import (
    M2706_MAX_CANONICAL_REQUEST_BYTES,
    ComplexActivitySecurityAccessResult,
    EvaluateComplexActivitySecurityAccessRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2706AuthorizationError
from .service import M2706Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2706Service()
_REQUEST_ADAPTER = TypeAdapter(EvaluateComplexActivitySecurityAccessRequest)
_RESULT_ADAPTER = TypeAdapter(ComplexActivitySecurityAccessResult)
_CONTRACT_NAMES = frozenset(
    {
        "request",
        "output",
        "access-decision",
        "audit-event",
        "posture",
        "control",
        "finding",
        "safe-failure",
    }
)


class M2706CliError(typer.BadParameter):
    """Sanitized M27-06 command-line error."""


def _read_request(path: Path) -> EvaluateComplexActivitySecurityAccessRequest:
    try:
        data = path.read_bytes()
        strict_json_loads(data, max_bytes=M2706_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2706CliError("input must satisfy the strict M27-06 request contract") from error  # noqa: TRY003


def _read_result(path: Path) -> ComplexActivitySecurityAccessResult:
    try:
        data = path.read_bytes()
        strict_json_loads(data)
        return _RESULT_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2706CliError("input must be a valid M27-06 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2706CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument()],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    if name not in _CONTRACT_NAMES:
        raise M2706CliError("unknown M27-06 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2706AuthorizationError) as error:
        raise M2706CliError("request does not satisfy the M27-06 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("evaluate")
def evaluate(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    try:
        result = _SERVICE.emit(_read_request(path))
    except (ValidationError, ValueError, M2706AuthorizationError) as error:
        raise M2706CliError("request was rejected by the M27-06 service") from error  # noqa: TRY003
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    result = _read_result(path)
    try:
        replay = _SERVICE.replay(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2706CliError("result replay is invalid") from error  # noqa: TRY003
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["M2706CliError", "app"]

"""Typer commands for strict M26-06 security evaluation and replay."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_06 import (
    M2606_MAX_CANONICAL_REQUEST_BYTES,
    M2606_MAX_CANONICAL_RESULT_BYTES,
    EvaluateProteomicsSecurityAccessRequest,
    ProteomicsSecurityAccessResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2606AuthorizationError, M2606ReplayError
from .service import M2606SecurityService

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2606SecurityService()
_REQUEST_ADAPTER: TypeAdapter[EvaluateProteomicsSecurityAccessRequest] = TypeAdapter(
    EvaluateProteomicsSecurityAccessRequest
)
_RESULT_ADAPTER: TypeAdapter[ProteomicsSecurityAccessResult] = TypeAdapter(
    ProteomicsSecurityAccessResult
)
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


class M2606CliError(typer.BadParameter):
    """Sanitized M26-06 command-line validation error."""


def _read_request(path: Path) -> EvaluateProteomicsSecurityAccessRequest:
    try:
        decoded = strict_json_loads(path.read_bytes(), max_bytes=M2606_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2606CliError("input must satisfy the strict M26-06 request contract") from error  # noqa: TRY003


def _read_result(path: Path) -> ProteomicsSecurityAccessResult:
    try:
        decoded = strict_json_loads(path.read_bytes(), max_bytes=M2606_MAX_CANONICAL_RESULT_BYTES)
        return _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2606CliError("input must be a valid M26-06 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2606CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="name of an M26-06 contract schema")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M26-06 schema."""

    if name not in _CONTRACT_NAMES:
        raise M2606CliError("unknown M26-06 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate an M26-06 request without evaluating access."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2606AuthorizationError) as error:
        raise M2606CliError("request does not satisfy the M26-06 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("evaluate")
def evaluate(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Evaluate security controls or return explicit safe abstention."""

    try:
        result = _SERVICE.execute(_read_request(path))
    except (ValidationError, ValueError, M2606AuthorizationError) as error:
        raise M2606CliError("request was rejected by the M26-06 security service") from error  # noqa: TRY003
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=3)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify one M26-06 result by canonical replay."""

    try:
        replay = _SERVICE.verify(_read_result(path))
    except (M2606ReplayError, TypeError, ValueError, ValidationError) as error:
        raise M2606CliError("result replay is invalid") from error  # noqa: TRY003
    typer.echo(
        json.dumps({"verified": True, "result_digest": replay.result_digest}, sort_keys=True)
    )


__all__ = ["M2606CliError", "app"]

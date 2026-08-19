"""Typer adapter for the provisional M26-03 pipeline orchestrator."""

# ruff: noqa: TRY003

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m26_03 import (
    M2603_MAX_CANONICAL_REQUEST_BYTES,
    M2603_MAX_CANONICAL_RESULT_BYTES,
    ExecuteProteinSubtypeWorkflowRequest,
    ProteinSubtypeExecutionResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2603AuthorizationError, M2603EvaluationError
from .service import M2603Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2603Service()
_REQUEST_ADAPTER = TypeAdapter(ExecuteProteinSubtypeWorkflowRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypeExecutionResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "step",
    "attempt",
    "execution",
    "package",
    "workflow",
    "environment",
    "finding",
}


class M2603CliError(typer.BadParameter):
    """Sanitized M26-03 command-line validation error."""


def _read_request(path: Path) -> ExecuteProteinSubtypeWorkflowRequest:
    try:
        data = read_bounded(path, M2603_MAX_CANONICAL_REQUEST_BYTES)
        strict_json_loads(data, max_bytes=M2603_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2603CliError("input must satisfy the strict M26-03 request contract") from error


def _read_result(path: Path) -> ProteinSubtypeExecutionResult:
    try:
        data = read_bounded(path, M2603_MAX_CANONICAL_RESULT_BYTES)
        strict_json_loads(data, max_bytes=M2603_MAX_CANONICAL_RESULT_BYTES)
        return _RESULT_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2603CliError("input must be a valid M26-03 result") from error


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2603CliError("output already exists; refusing to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[
        str,
        typer.Argument(
            help=("request, output, attempt, execution, package, workflow, environment, or finding")
        ),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M26-03 contract schema."""
    if name not in _CONTRACT_NAMES:
        raise M2603CliError("unknown M26-03 contract")
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate one workflow request without executing it."""
    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2603AuthorizationError) as error:
        raise M2603CliError("request does not satisfy the M26-03 contract") from error
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("execute")
def execute(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Execute one deterministic workflow and emit its canonical result."""
    try:
        result = _SERVICE.execute(_read_request(path))
    except (ValidationError, ValueError, M2603AuthorizationError, M2603EvaluationError) as error:
        raise M2603CliError("request was rejected by the M26-03 service") from error
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify one immutable workflow result by replaying its canonical digest."""
    result = _read_result(path)
    try:
        replay = _SERVICE.verify(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2603CliError("result replay is invalid") from error
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["app"]

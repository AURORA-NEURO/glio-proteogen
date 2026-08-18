"""Typer adapter for provisional M23-04 external transport evaluation."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m23_04 import (
    M2304_MAX_CANONICAL_REQUEST_BYTES,
    M2304_MAX_CANONICAL_RESULT_BYTES,
    EvaluateVariantPeptideExternalTransportRequest,
    VariantPeptideExternalTransportResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2304AuthorizationError
from .service import M2304Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2304Service()
_REQUEST_ADAPTER = TypeAdapter(EvaluateVariantPeptideExternalTransportRequest)
_RESULT_ADAPTER = TypeAdapter(VariantPeptideExternalTransportResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "validation",
    "evaluation",
    "support-domain-update",
    "configuration",
    "report",
    "finding",
}


class M2304CliError(typer.BadParameter):
    """Sanitized M23-04 command-line validation error."""


def _read_request(path: Path) -> EvaluateVariantPeptideExternalTransportRequest:
    try:
        data = read_bounded(path, M2304_MAX_CANONICAL_REQUEST_BYTES)
        parsed = strict_json_loads(data, max_bytes=M2304_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2304CliError(  # noqa: TRY003
            "input must satisfy the strict M23-04 request contract"
        ) from error


def _read_result(path: Path) -> VariantPeptideExternalTransportResult:
    try:
        parsed = strict_json_loads(
            read_bounded(path, M2304_MAX_CANONICAL_RESULT_BYTES),
            max_bytes=M2304_MAX_CANONICAL_RESULT_BYTES,
        )
        return _RESULT_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2304CliError("input must be a valid M23-04 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2304CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[
        str,
        typer.Argument(
            help=(
                "request, output, validation, evaluation, support-domain-update, "
                "configuration, report, or finding"
            )
        ),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M23-04 contract schema."""

    if name not in _CONTRACT_NAMES:
        raise M2304CliError("unknown M23-04 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate one transport request without executing it."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2304AuthorizationError) as error:
        raise M2304CliError("request does not satisfy the M23-04 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("evaluate")
def evaluate(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Evaluate external transport and emit one canonical result."""

    try:
        result = _SERVICE.evaluate(_read_request(path))
    except (ValidationError, ValueError, M2304AuthorizationError) as error:
        raise M2304CliError("request was rejected by the M23-04 service") from error  # noqa: TRY003
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify one immutable transport result by replaying its digest."""

    result = _read_result(path)
    try:
        replay = _SERVICE.verify_replay(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2304CliError("result replay is invalid") from error  # noqa: TRY003
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["app"]

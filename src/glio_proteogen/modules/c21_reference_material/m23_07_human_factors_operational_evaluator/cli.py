"""Typer adapter for provisional M23-07 operational evaluation."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m23_07 import (
    M2307_MAX_CANONICAL_REQUEST_BYTES,
    M2307_MAX_CANONICAL_RESULT_BYTES,
    EvaluateVariantPeptideHumanFactorsRequest,
    VariantPeptideHumanFactorsResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2307AuthorizationError
from .service import M2307Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2307Service()
_REQUEST_ADAPTER = TypeAdapter(EvaluateVariantPeptideHumanFactorsRequest)
_RESULT_ADAPTER = TypeAdapter(VariantPeptideHumanFactorsResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "report",
    "metric",
    "fallback",
    "configuration",
    "finding",
}


class M2307CliError(typer.BadParameter):
    """Sanitized M23-07 command-line validation error."""


def _read_request(path: Path) -> EvaluateVariantPeptideHumanFactorsRequest:
    try:
        data = read_bounded(path, M2307_MAX_CANONICAL_REQUEST_BYTES)
        strict_json_loads(data, max_bytes=M2307_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2307CliError(  # noqa: TRY003
            "input must satisfy the strict M23-07 request contract"
        ) from error


def _read_result(path: Path) -> VariantPeptideHumanFactorsResult:
    try:
        return _RESULT_ADAPTER.validate_json(
            read_bounded(path, M2307_MAX_CANONICAL_RESULT_BYTES), strict=True
        )
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2307CliError("input must be a valid M23-07 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2307CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[
        str,
        typer.Argument(help="request, output, report, metric, fallback, configuration, or finding"),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M23-07 contract schema."""

    if name not in _CONTRACT_NAMES:
        raise M2307CliError("unknown M23-07 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate one operational evaluation request without executing it."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2307AuthorizationError) as error:
        raise M2307CliError("request does not satisfy the M23-07 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("evaluate")
def evaluate(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Evaluate caller-declared human-factors and operational material."""

    try:
        result = _SERVICE.evaluate(_read_request(path))
    except (ValidationError, ValueError, M2307AuthorizationError) as error:
        raise M2307CliError("request was rejected by the M23-07 service") from error  # noqa: TRY003
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify one immutable operational result by replaying its digest."""

    result = _read_result(path)
    try:
        replay = _SERVICE.replay(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2307CliError("result replay is invalid") from error  # noqa: TRY003
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["app"]

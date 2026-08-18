"""Typer adapter for provisional M22-03 benchmark execution."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m22_03 import (
    M2203_MAX_CANONICAL_REQUEST_BYTES,
    M2203_MAX_CANONICAL_RESULT_BYTES,
    ProteinRnaDiscordanceInternalBenchmarkResult,
    RunProteinRnaDiscordanceInternalBenchmarkRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2203AuthorizationError
from .service import M2203Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2203Service()
_REQUEST_ADAPTER = TypeAdapter(RunProteinRnaDiscordanceInternalBenchmarkRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinRnaDiscordanceInternalBenchmarkResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "dossier",
    "split",
    "baseline",
    "metric",
    "ablation",
    "comparison",
    "finding",
}


class M2203CliError(typer.BadParameter):
    """Sanitized M22-03 command-line validation error."""


def _read_request(path: Path) -> RunProteinRnaDiscordanceInternalBenchmarkRequest:
    try:
        data = read_bounded(path, M2203_MAX_CANONICAL_REQUEST_BYTES)
        strict_json_loads(data, max_bytes=M2203_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2203CliError(  # noqa: TRY003
            "input must satisfy the strict M22-03 request contract"
        ) from error


def _read_result(path: Path) -> ProteinRnaDiscordanceInternalBenchmarkResult:
    try:
        return _RESULT_ADAPTER.validate_json(
            read_bounded(path, M2203_MAX_CANONICAL_RESULT_BYTES), strict=True
        )
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2203CliError("input must be a valid M22-03 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2203CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[
        str,
        typer.Argument(
            help=(
                "request, output, dossier, split, baseline, metric, ablation, comparison, "
                "or finding"
            )
        ),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M22-03 contract schema."""

    if name not in _CONTRACT_NAMES:
        raise M2203CliError("unknown M22-03 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate one benchmark request without executing it."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2203AuthorizationError) as error:
        raise M2203CliError("request does not satisfy the M22-03 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("benchmark")
def benchmark(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Run the metadata-only benchmark and emit one canonical result."""

    try:
        result = _SERVICE.generate(_read_request(path))
    except (ValidationError, ValueError, M2203AuthorizationError) as error:
        raise M2203CliError("request was rejected by the M22-03 service") from error  # noqa: TRY003
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify one immutable benchmark result by replaying its digest."""

    result = _read_result(path)
    try:
        replay = _SERVICE.replay(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2203CliError("result replay is invalid") from error  # noqa: TRY003
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["app"]

"""Typer adapter for provisional M24-05 subgroup equity evaluation."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m24_05 import (
    M2405_MAX_CANONICAL_REQUEST_BYTES,
    BiomarkerPanelSubgroupEvaluationResult,
    EvaluateBiomarkerPanelSubgroupEquityRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2405AuthorizationError
from .service import M2405Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2405Service()
_REQUEST_ADAPTER = TypeAdapter(EvaluateBiomarkerPanelSubgroupEquityRequest)
_RESULT_ADAPTER = TypeAdapter(BiomarkerPanelSubgroupEvaluationResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "report",
    "performance",
    "calibration",
    "coverage",
    "configuration",
    "finding",
}


class M2405CliError(typer.BadParameter):
    """Sanitized M24-05 command-line validation error."""


def _read_request(path: Path) -> EvaluateBiomarkerPanelSubgroupEquityRequest:
    try:
        data = path.read_bytes()
        strict_json_loads(data, max_bytes=M2405_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2405CliError("input must satisfy the strict M24-05 request contract") from error  # noqa: TRY003


def _read_result(path: Path) -> BiomarkerPanelSubgroupEvaluationResult:
    try:
        return _RESULT_ADAPTER.validate_json(path.read_bytes(), strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2405CliError("input must be a valid M24-05 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2405CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[
        str,
        typer.Argument(
            help=(
                "request, output, report, performance, calibration, coverage, "
                "configuration, or finding"
            )
        ),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M24-05 contract schema."""

    if name not in _CONTRACT_NAMES:
        raise M2405CliError("unknown M24-05 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate one request without executing it."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2405AuthorizationError) as error:
        raise M2405CliError("request does not satisfy the M24-05 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("evaluate")
def evaluate(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Evaluate one request and emit a canonical subgroup result envelope."""

    try:
        result = _SERVICE.evaluate(_read_request(path))
    except (ValidationError, ValueError, M2405AuthorizationError) as error:
        raise M2405CliError("request was rejected by the M24-05 service") from error  # noqa: TRY003
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify one immutable result envelope by replaying its digest."""

    result = _read_result(path)
    try:
        replay = _SERVICE.verify_replay(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2405CliError("result replay is invalid") from error  # noqa: TRY003
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["app"]

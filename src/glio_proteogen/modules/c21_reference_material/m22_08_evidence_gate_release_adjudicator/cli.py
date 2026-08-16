"""Typer adapter for provisional M22-08 evidence adjudication."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m22_08 import (
    M2208_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
    ProteinRnaDiscordanceEvidenceGateResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2208AuthorizationError
from .service import M2208Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2208Service()
_REQUEST_ADAPTER = TypeAdapter(AdjudicateProteinRnaDiscordanceEvidenceGateRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinRnaDiscordanceEvidenceGateResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "requirement",
    "benchmark",
    "risk",
    "approval",
    "release-record",
    "configuration",
    "obligation",
    "finding",
}


class M2208CliError(typer.BadParameter):
    """Sanitized M22-08 command-line validation error."""


def _read_request(path: Path) -> AdjudicateProteinRnaDiscordanceEvidenceGateRequest:
    try:
        data = path.read_bytes()
        strict_json_loads(data, max_bytes=M2208_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2208CliError(  # noqa: TRY003
            "input must satisfy the strict M22-08 request contract"
        ) from error


def _read_result(path: Path) -> ProteinRnaDiscordanceEvidenceGateResult:
    try:
        return _RESULT_ADAPTER.validate_json(path.read_bytes(), strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2208CliError("input must be a valid M22-08 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2208CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[
        str,
        typer.Argument(
            help=(
                "request, output, requirement, benchmark, risk, approval, release-record, "
                "configuration, obligation, or finding"
            )
        ),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M22-08 contract schema."""

    if name not in _CONTRACT_NAMES:
        raise M2208CliError("unknown M22-08 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate one evidence-gate request without adjudicating it."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2208AuthorizationError) as error:
        raise M2208CliError(  # noqa: TRY003
            "request does not satisfy the M22-08 contract"
        ) from error
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("adjudicate")
def adjudicate(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Adjudicate evidence and emit one canonical release record."""

    try:
        result = _SERVICE.adjudicate(_read_request(path))
    except (ValidationError, ValueError, M2208AuthorizationError) as error:
        raise M2208CliError(  # noqa: TRY003
            "request was rejected by the M22-08 service"
        ) from error
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify one immutable M22-08 result by replaying its digest."""

    result = _read_result(path)
    try:
        replay = _SERVICE.replay(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2208CliError("result replay is invalid") from error  # noqa: TRY003
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["app"]

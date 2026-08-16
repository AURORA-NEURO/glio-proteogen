"""Typer commands for strict M23-08 evidence-gate operations."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m23_08 import (
    M2308_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateVariantPeptideEvidenceGateRequest,
    VariantPeptideEvidenceGateResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2308AuthorizationError
from .service import M2308Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2308Service()
_REQUEST_ADAPTER = TypeAdapter(AdjudicateVariantPeptideEvidenceGateRequest)
_RESULT_ADAPTER = TypeAdapter(VariantPeptideEvidenceGateResult)
_CONTRACT_NAMES = frozenset(
    {
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
)


class M2308CliError(typer.BadParameter):
    """Sanitized M23-08 command-line validation error."""


def _read_request(path: Path) -> AdjudicateVariantPeptideEvidenceGateRequest:
    try:
        data = path.read_bytes()
        strict_json_loads(data, max_bytes=M2308_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2308CliError(  # noqa: TRY003
            "input must satisfy the strict M23-08 request contract"
        ) from error


def _read_result(path: Path) -> VariantPeptideEvidenceGateResult:
    try:
        data = path.read_bytes()
        strict_json_loads(data)
        return _RESULT_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2308CliError("input must be a valid M23-08 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2308CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument(help="name of a M23-08 contract schema")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional M23-08 schema."""

    if name not in _CONTRACT_NAMES:
        raise M2308CliError("unknown M23-08 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate a caller-declared gate request without adjudicating it."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M2308AuthorizationError) as error:
        raise M2308CliError(  # noqa: TRY003
            "request does not satisfy the M23-08 contract"
        ) from error
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("adjudicate")
def adjudicate(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Adjudicate gate material and emit a canonical result."""

    try:
        result = _SERVICE.adjudicate(_read_request(path))
    except (ValidationError, ValueError, M2308AuthorizationError) as error:
        raise M2308CliError("request was rejected by the M23-08 service") from error  # noqa: TRY003
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)
    if result.status.value == "abstained":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify an immutable M23-08 result by canonical replay."""

    result = _read_result(path)
    try:
        replay = _SERVICE.replay(result)
    except (TypeError, ValueError, ValidationError) as error:
        raise M2308CliError("result replay is invalid") from error  # noqa: TRY003
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["M2308CliError", "app"]

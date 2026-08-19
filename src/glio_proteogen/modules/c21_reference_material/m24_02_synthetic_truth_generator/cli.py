"""Typer adapter for provisional M24-02 synthetic truth generation."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m24_02 import (
    M2402_MAX_CANONICAL_REQUEST_BYTES,
    M2402_MAX_CANONICAL_RESULT_BYTES,
    BiomarkerPanelSyntheticTruthResult,
    GenerateBiomarkerPanelSyntheticTruthRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import AuthorizationError
from .service import M2402Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M2402Service()
_REQUEST_ADAPTER = TypeAdapter(GenerateBiomarkerPanelSyntheticTruthRequest)
_RESULT_ADAPTER = TypeAdapter(BiomarkerPanelSyntheticTruthResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "corpus",
    "case",
    "manifest",
    "configuration",
    "finding",
}


class M2402CliError(typer.BadParameter):
    """Sanitized M24-02 command-line error."""


def _read_request(path: Path) -> GenerateBiomarkerPanelSyntheticTruthRequest:
    try:
        data = read_bounded(path, M2402_MAX_CANONICAL_REQUEST_BYTES)
        strict_json_loads(data, max_bytes=M2402_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2402CliError(  # noqa: TRY003
            "input must satisfy the strict M24-02 request contract"
        ) from error


def _read_result(path: Path) -> BiomarkerPanelSyntheticTruthResult:
    try:
        data = read_bounded(path, M2402_MAX_CANONICAL_RESULT_BYTES)
        value = strict_json_loads(data, max_bytes=M2402_MAX_CANONICAL_RESULT_BYTES)
        return _RESULT_ADAPTER.validate_json(canonical_json_bytes(value), strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise M2402CliError("input must be a valid M24-02 result") from error  # noqa: TRY003


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise M2402CliError("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@app.command("export-schema")
def export_schema(
    name: Annotated[str, typer.Argument()],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    if name not in _CONTRACT_NAMES:
        raise M2402CliError("unknown M24-02 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode())
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    try:
        typed = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, AuthorizationError) as error:
        raise M2402CliError("request does not satisfy the M24-02 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(typed.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("generate")
def generate(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    try:
        result = _SERVICE.evaluate(_read_request(path))
    except (ValidationError, ValueError, AuthorizationError) as error:
        raise M2402CliError("request was rejected by the M24-02 service") from error  # noqa: TRY003
    data = canonical_json_bytes(result)
    if output is None:
        typer.echo(data.decode())
    else:
        _write_new(output, data)


@app.command("verify")
def verify(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    try:
        result = _read_result(path)
        replay = _SERVICE.verify_replay(result)
    except (OSError, TypeError, ValueError, ValidationError) as error:
        raise M2402CliError("result replay is invalid") from error  # noqa: TRY003
    verified = replay.result_digest == result.result_digest
    typer.echo(
        json.dumps({"verified": verified, "result_digest": replay.result_digest}, sort_keys=True)
    )
    if not verified:
        raise typer.Exit(code=1)


__all__ = ["app"]

"""Typer commands for strict M19-07 export and replay."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003
from typing import Annotated

import typer
from pydantic import TypeAdapter

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m19_07 import (
    M1907_MAX_CANONICAL_REQUEST_BYTES,
    M1907_MAX_CANONICAL_RESULT_BYTES,
    ContractName,
    ExportProteotypeDownstreamContractRequest,
    ProteotypeDownstreamExportResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .service import M1907Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_REQUEST_ADAPTER = TypeAdapter(ExportProteotypeDownstreamContractRequest)
_RESULT_ADAPTER = TypeAdapter(ProteotypeDownstreamExportResult)


def _read_request(path: Path) -> ExportProteotypeDownstreamContractRequest:
    decoded = strict_json_loads(
        read_bounded(path, M1907_MAX_CANONICAL_REQUEST_BYTES),
        max_bytes=M1907_MAX_CANONICAL_REQUEST_BYTES,
    )
    return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)


def _read_result(path: Path) -> ProteotypeDownstreamExportResult:
    decoded = strict_json_loads(
        read_bounded(path, M1907_MAX_CANONICAL_RESULT_BYTES),
        max_bytes=M1907_MAX_CANONICAL_RESULT_BYTES,
    )
    return _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)


def _write_json(path: Path, value: object, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise typer.BadParameter("output exists; pass --overwrite to replace it")  # noqa: TRY003
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@app.command("export-schema")
def export_schema(
    name: Annotated[ContractName, typer.Argument()],
    output: Annotated[Path, typer.Option("--output", "-o")],
    overwrite: Annotated[bool, typer.Option("--overwrite")] = False,  # noqa: FBT002
) -> None:
    """Write one strict M19-07 JSON schema without accidental overwrite."""

    _write_json(output, contract_json_schema(name), overwrite=overwrite)


@app.command("validate")
def validate(input_path: Annotated[Path, typer.Argument()]) -> None:
    """Strictly parse and validate one request."""

    request = _read_request(input_path)
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True))


@app.command("export")
def export(input_path: Annotated[Path, typer.Argument()]) -> None:
    """Execute one validated downstream export."""

    result = M1907Service().execute(_read_request(input_path))
    typer.echo(json.dumps(result.model_dump(mode="json"), sort_keys=True))


@app.command("verify")
def verify(input_path: Annotated[Path, typer.Argument()]) -> None:
    """Verify result digest and deterministic replay."""

    result = _read_result(input_path)
    verified = M1907Service().verify(result)
    typer.echo(json.dumps(verified.model_dump(mode="json"), sort_keys=True))


__all__ = ["app"]

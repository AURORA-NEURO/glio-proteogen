"""Typer adapter for M26-02 schema, validation, construction, and replay."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - used for filesystem operations.
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_02 import (
    BuildProteinSubtypeLineageRequest,
    ProteinSubtypeLineageResult,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import sanitized_validation_errors, strict_json_loads
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.service import (
    M2602LineageService,
)

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_REQUEST_ADAPTER: TypeAdapter[BuildProteinSubtypeLineageRequest] = TypeAdapter(
    BuildProteinSubtypeLineageRequest
)
_RESULT_ADAPTER: TypeAdapter[ProteinSubtypeLineageResult] = TypeAdapter(ProteinSubtypeLineageResult)


def _read(path: Path) -> bytes:
    return path.read_bytes()


def _request(path: Path) -> object:
    try:
        return strict_json_loads(_read(path))
    except ValueError as error:
        raise typer.BadParameter("input is not strict JSON") from error  # noqa: TRY003


def _validated_request(path: Path) -> BuildProteinSubtypeLineageRequest:
    raw = _read(path)
    strict_json_loads(raw)
    return _REQUEST_ADAPTER.validate_json(raw, strict=True)


def _validated_result(path: Path) -> ProteinSubtypeLineageResult:
    raw = _read(path)
    strict_json_loads(raw)
    return _RESULT_ADAPTER.validate_json(raw, strict=True)


@app.command("export-schema")
def export_schema(
    name: Annotated[
        str, typer.Argument(help="request, output, node, edge, graph, bundle, or finding")
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict M26-02 JSON Schema without overwriting files."""

    try:
        document = contract_json_schema(name)  # type: ignore[arg-type]
    except KeyError as error:
        raise typer.BadParameter("unknown M26-02 schema") from error  # noqa: TRY003
    encoded = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if output is None:
        typer.echo(encoded, nl=False)
        return
    if output.exists():
        raise typer.BadParameter(  # noqa: TRY003
            "output already exists; refusing to overwrite"
        )
    output.write_text(encoded, encoding="utf-8", newline="\n")


@app.command("validate")
def validate(input_path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate a request using the same strict parser as the plugin and API."""

    try:
        M2602LineageService.validate_request(_validated_request(input_path))
    except (ValueError, ValidationError) as error:
        details = (
            sanitized_validation_errors(error)
            if isinstance(error, ValidationError)
            else [{"msg": str(error)}]
        )
        typer.echo(json.dumps({"valid": False, "errors": details}, sort_keys=True), err=True)
        raise typer.Exit(code=2) from error
    typer.echo(json.dumps({"valid": True}, sort_keys=True))


@app.command("construct")
def construct(
    input_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Construct a result; abstentions are reported and never written as success."""

    if output is not None and output.exists():
        raise typer.BadParameter(  # noqa: TRY003
            "output already exists; refusing to overwrite"
        )
    try:
        result = M2602LineageService().execute(_validated_request(input_path))
    except (ValueError, ValidationError) as error:
        typer.echo(json.dumps({"valid": False, "errors": [{"msg": str(error)}]}), err=True)
        raise typer.Exit(code=2) from error
    encoded = json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if output is None:
        typer.echo(encoded, nl=False)
    else:
        output.write_text(encoded, encoding="utf-8", newline="\n")
    if result.status.value != "built":
        raise typer.Exit(code=3)


@app.command("verify")
def verify(input_path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify a canonical result and its replay bindings."""

    try:
        result = M2602LineageService.verify(_validated_result(input_path))
    except (ValueError, ValidationError) as error:
        typer.echo(json.dumps({"verified": False, "error": str(error)}), err=True)
        raise typer.Exit(code=2) from error
    typer.echo(json.dumps({"verified": True, "resultDigest": result.result_digest}, sort_keys=True))


__all__ = ["app", "construct", "export_schema", "validate", "verify"]

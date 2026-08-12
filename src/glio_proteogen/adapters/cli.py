"""Human-readable and automation-safe command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

import typer
import uvicorn
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.api import _contract_schema, create_app
from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.contracts.m01_01.v1 import (
    EvaluateMetadataRequest,
    RegisterProtocolRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    assert_strict_json,
    sanitized_validation_errors,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    M0101EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    InvalidProtocolLookupError,
    M0101Service,
    M0101ServiceError,
)

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
protocol_app = typer.Typer(no_args_is_help=True, help="M01-01 protocol operations.")
app.add_typer(protocol_app, name="protocol")

DatabaseOption = Annotated[
    Path,
    typer.Option("--database", "-d", help="Append-only SQLite event database."),
]
RequestArgument = Annotated[
    Path,
    typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
]


def _emit(value: object) -> None:
    typer.echo(canonical_json_bytes(value).decode("utf-8"))


def _load_request[RequestT](path: Path, adapter: TypeAdapter[RequestT]) -> RequestT:
    try:
        payload = read_bounded(path)
        assert_strict_json(payload)
        return adapter.validate_json(payload, strict=True)
    except RequestBodyTooLargeError as error:
        typer.echo(f"invalid request: {error}", err=True)
        raise typer.Exit(code=2) from error
    except StrictJsonError as error:
        typer.echo(f"invalid request: {error} ({error.code.value})", err=True)
        raise typer.Exit(code=2) from error
    except ValidationError as error:
        details = canonical_json_bytes(sanitized_validation_errors(error)).decode("utf-8")
        typer.echo(f"invalid request: {details}", err=True)
        raise typer.Exit(code=2) from error
    except (OSError, ValueError) as error:
        typer.echo("invalid request: unable to read or decode request document", err=True)
        raise typer.Exit(code=2) from error


def _service(database: Path) -> M0101Service:
    return M0101Service(M0101EventStore(database))


@protocol_app.command("register")
def register_protocol(request: RequestArgument, database: DatabaseOption) -> None:
    """Register an immutable protocol specification."""

    parsed = _load_request(request, TypeAdapter(RegisterProtocolRequest))
    try:
        with _service(database) as service:
            _emit(service.register(parsed))
    except M0101ServiceError as error:
        typer.echo(f"registration failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@protocol_app.command("evaluate")
def evaluate_metadata(request: RequestArgument, database: DatabaseOption) -> None:
    """Evaluate metadata without mutating the submitted evidence."""

    parsed = _load_request(request, TypeAdapter(EvaluateMetadataRequest))
    try:
        with _service(database) as service:
            _emit(service.evaluate(parsed))
    except M0101ServiceError as error:
        typer.echo(f"evaluation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@protocol_app.command("get")
def get_protocol(
    schema_id: Annotated[str, typer.Argument(help="Protocol schema identifier.")],
    version: Annotated[str, typer.Argument(help="Exact semantic version.")],
    database: DatabaseOption,
) -> None:
    """Retrieve the original content-addressed registration receipt."""

    try:
        with _service(database) as service:
            _emit(service.get_protocol(schema_id, version))
    except InvalidProtocolLookupError as error:
        typer.echo(f"invalid lookup: {error}", err=True)
        raise typer.Exit(code=2) from error
    except M0101ServiceError as error:
        typer.echo(f"lookup failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@protocol_app.command("verify-ledger")
def verify_ledger(database: DatabaseOption) -> None:
    """Verify every link and payload digest in the append-only event chain."""

    try:
        with _service(database) as service:
            result = service.verify_event_chain()
            _emit(result)
            if not result.valid:
                raise typer.Exit(code=1)
    except M0101ServiceError as error:
        typer.echo(f"verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@app.command("export-schema")
def export_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "register-request",
            "evaluate-request",
            "protocol-schema",
            "metadata-document",
            "protocol-receipt",
            "conformance-profile",
        ],
        typer.Argument(help="Public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable public contract for agents and tools."""

    typer.echo(json.dumps(_contract_schema(contract), indent=2, sort_keys=True))


@app.command("serve")
def serve(
    database: DatabaseOption,
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65_535, help="Bind port.")] = 8000,
) -> None:
    """Run the typed research API."""

    uvicorn.run(create_app(database), host=host, port=port)


if __name__ == "__main__":
    app()

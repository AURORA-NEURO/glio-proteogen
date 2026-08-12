"""Human-readable and automation-safe command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import typer
import uvicorn
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.api import (
    _contract_schema,
    _identity_contract_schema,
    _quality_contract_schema,
    _raw_contract_schema,
    create_app,
)
from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.contracts.m01_01.v1 import (
    EvaluateMetadataRequest,
    RegisterProtocolRequest,
)
from glio_proteogen.contracts.m01_02.v1 import ReconcileIdentityLineageRequest
from glio_proteogen.contracts.m01_04.v1 import ComputeQualityMetricsRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import Identifier, Sha256Digest
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    M0101EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    InvalidProtocolLookupError,
    M0101Service,
    M0101ServiceError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    EventStoreError as M0102EventStoreError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    IdentityLineageAuthorizationError,
    M0102Service,
    preflight_identity_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion.parser import (
    parse_raw_input,
)
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.service import (
    M0104Service,
)

if TYPE_CHECKING:
    from collections.abc import Callable

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
protocol_app = typer.Typer(no_args_is_help=True, help="M01-01 protocol operations.")
app.add_typer(protocol_app, name="protocol")
identity_app = typer.Typer(no_args_is_help=True, help="M01-02 identity and lineage operations.")
app.add_typer(identity_app, name="identity")
raw_app = typer.Typer(no_args_is_help=True, help="M01-03 bounded raw-format ingestion.")
app.add_typer(raw_app, name="raw")
quality_app = typer.Typer(no_args_is_help=True, help="M01-04 deterministic quality metrics.")
app.add_typer(quality_app, name="quality")

_RESOLUTION_DIGEST_ADAPTER = TypeAdapter(Sha256Digest)

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


def _load_request[RequestT](
    path: Path,
    adapter: TypeAdapter[RequestT],
    preflight: Callable[[object], None] | None = None,
) -> RequestT:
    try:
        payload = read_bounded(path)
        decoded = strict_json_loads(payload)
        if preflight is not None:
            preflight(decoded)
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


def _identity_service(database: Path) -> M0102Service:
    return M0102Service(M0102EventStore(database))


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


@identity_app.command("reconcile")
def reconcile_identity_lineage(request: RequestArgument, database: DatabaseOption) -> None:
    """Reconcile explicit identity assertions and lineage without relabeling inputs."""

    try:
        parsed = _load_request(
            request,
            TypeAdapter(ReconcileIdentityLineageRequest),
            preflight_identity_authorization,
        )
        with _identity_service(database) as service:
            _emit(service.execute(parsed))
    except (IdentityLineageAuthorizationError, M0102EventStoreError) as error:
        typer.echo(f"reconciliation failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@identity_app.command("get")
def get_identity_resolution(
    resolution_digest: Annotated[str, typer.Argument(help="Exact resolution digest.")],
    database: DatabaseOption,
) -> None:
    """Retrieve and revalidate an immutable identity-lineage resolution."""

    try:
        validated_digest = _RESOLUTION_DIGEST_ADAPTER.validate_python(
            resolution_digest,
            strict=True,
        )
    except ValidationError as error:
        typer.echo("invalid lookup: resolution digest is invalid", err=True)
        raise typer.Exit(code=2) from error
    try:
        with _identity_service(database) as service:
            _emit(service.get_resolution(validated_digest))
    except M0102EventStoreError as error:
        typer.echo(f"lookup failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@identity_app.command("verify-ledger")
def verify_identity_ledger(database: DatabaseOption) -> None:
    """Verify the M01-02 append-only identity-resolution event chain."""

    try:
        with _identity_service(database) as service:
            result = service.verify_event_chain()
            _emit(result)
            if not result.valid:
                raise typer.Exit(code=1)
    except M0102EventStoreError as error:
        typer.echo(f"verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error


@identity_app.command("export-schema")
def export_identity_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "entity", "operation", "resolution"],
        typer.Argument(help="M01-02 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-02 contract for agents and tools."""

    typer.echo(json.dumps(_identity_contract_schema(contract), indent=2, sort_keys=True))


@raw_app.command("inspect")
def inspect_raw_input(
    source: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True),
    ],
    source_id: Annotated[str, typer.Option("--source-id", help="Opaque source identifier.")],
    expected_sha256: Annotated[
        str | None,
        typer.Option("--sha256", help="Optional SHA-256 digest of the transported bytes."),
    ] = None,
) -> None:
    """Inspect one bounded file and emit metadata only; source content is never echoed."""

    try:
        validated_source_id = TypeAdapter(Identifier).validate_python(source_id, strict=True)
        with source.open("rb") as stream:
            result = parse_raw_input(
                stream,
                source_id=validated_source_id,
                filename=source.name,
                expected_sha256=expected_sha256,
            )
    except ValidationError as error:
        typer.echo("invalid source identifier", err=True)
        raise typer.Exit(code=2) from error
    except OSError as error:
        typer.echo("inspection failed: unable to read source", err=True)
        raise typer.Exit(code=1) from error
    _emit(result)
    if result.disposition.value != "accepted":
        raise typer.Exit(code=1)


@raw_app.command("export-schema")
def export_raw_schema(
    contract: Annotated[
        Literal["request", "output", "policy", "source", "raw_input", "diagnostic"],
        typer.Argument(help="M01-03 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-03 contract for agents and tools."""

    typer.echo(json.dumps(_raw_contract_schema(contract), indent=2, sort_keys=True))


@quality_app.command("compute")
def compute_quality_metrics(request: RequestArgument) -> None:
    """Compute one deterministic typed quality profile."""

    parsed = _load_request(request, TypeAdapter(ComputeQualityMetricsRequest))
    _emit(M0104Service().execute(parsed))


@quality_app.command("export-schema")
def export_quality_schema(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "policy",
            "assay_profile",
            "metric_definition",
            "observation",
            "quality_metric",
        ],
        typer.Argument(help="M01-04 public contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    """Export a machine-readable M01-04 contract for agents and tools."""

    typer.echo(json.dumps(_quality_contract_schema(contract), indent=2, sort_keys=True))


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

"""Typer CLI for strict M05-08 validation and quarantine-first builds."""

# CLI diagnostics intentionally collapse internal errors into stable user-facing
# messages; those raises are the command boundary.
# ruff: noqa: TRY003, TRY300

from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path  # noqa: TC003 - Typer resolves this runtime annotation.
from typing import Annotated, Final

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m05_08 import (
    M0508_MAX_CANONICAL_REQUEST_BYTES,
    BuildPtmLocalizationReleaseRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.service import (
    M0508Service,
)

_REQUEST_ADAPTER: Final = TypeAdapter(BuildPtmLocalizationReleaseRequest)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "policy",
        "artifact",
        "manifest",
        "signature",
        "quarantine",
        "verification",
        "transformation",
        "quality-decision",
    }
)

app = typer.Typer(help="M05-08 provenance and release packaging.")


def _read(path: Path) -> bytes:
    try:
        body = path.read_bytes()
        strict_json_loads(body, max_bytes=M0508_MAX_CANONICAL_REQUEST_BYTES)
        return body
    except (OSError, StrictJsonError) as error:
        raise typer.BadParameter("request is not bounded strict JSON") from error


def _request_from_file(path: Path) -> BuildPtmLocalizationReleaseRequest:
    body = _read(path)
    try:
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except ValidationError as error:
        raise typer.BadParameter("request does not match the M05-08 contract") from error


def _artifacts_from_document(document: object) -> dict[str, bytes]:
    if not isinstance(document, dict):
        raise typer.BadParameter("build input must be an object")
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, dict):
        raise typer.BadParameter("build input requires base64 artifacts")
    decoded: dict[str, bytes] = {}
    for path, value in artifacts.items():
        if not isinstance(path, str) or not isinstance(value, str):
            raise typer.BadParameter("artifact paths and values must be strings")
        try:
            decoded[path] = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as error:
            raise typer.BadParameter("artifact values must be valid base64") from error
    return decoded


@app.command("export-schema")
def export_schema(
    contract: Annotated[str, typer.Argument(help="M05-08 contract name.")],
) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    if contract not in _CONTRACT_NAMES:
        raise typer.BadParameter("unknown M05-08 contract")
    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))  # type: ignore[arg-type]


@app.command("validate")
def validate(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Parse and validate one request exactly once before emitting canonical JSON."""

    typer.echo(canonical_json_bytes(_request_from_file(request).model_dump(mode="json")).decode())


@app.command("build")
def build(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option(help="Optional new result JSON path.")] = None,
) -> None:
    """Build with the default verifier-free service; unsupported release stays quarantined."""

    body = _read(request)
    try:
        document = strict_json_loads(body, max_bytes=M0508_MAX_CANONICAL_REQUEST_BYTES)
        if not isinstance(document, dict) or not isinstance(document.get("request"), dict):
            raise typer.BadParameter("build input requires a request object")
        typed = _REQUEST_ADAPTER.validate_json(
            canonical_json_bytes(document["request"]), strict=True
        )
        built = M0508Service().build(typed, _artifacts_from_document(document))
    except (ValidationError, ValueError, TypeError, StrictJsonError) as error:
        raise typer.BadParameter("build input is invalid") from error
    payload = {
        "result": built.result.model_dump(mode="json"),
        "package": (
            base64.b64encode(built.package_bytes).decode("ascii")
            if built.package_bytes is not None
            else None
        ),
    }
    encoded = canonical_json_bytes(payload)
    if output is None:
        typer.echo(encoded.decode())
    else:
        if output.exists():
            raise typer.BadParameter("output already exists")
        output.write_bytes(encoded)
    if built.result.disposition.value != "released":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()


__all__ = ["app"]

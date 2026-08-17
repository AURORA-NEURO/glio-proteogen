"""Typer CLI for strict M08-08 validation and publishing."""

# CLI diagnostics intentionally collapse internal exceptions into stable messages.
# ruff: noqa: TRY003, TRY300

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Final

import typer
from pydantic import TypeAdapter, ValidationError

if __package__ in {None, ""}:
    _SOURCE_ROOT = Path(__file__).resolve().parents[4]
    if str(_SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SOURCE_ROOT))

from glio_proteogen.contracts.m08_08 import (
    M0808_MAX_CANONICAL_REQUEST_BYTES,
    PublishTranscriptProteinEvidenceRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_08_evidence_explanation_publisher.engine import (  # noqa: E501
    M0808AuthorizationError,
)
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_08_evidence_explanation_publisher.service import (  # noqa: E501
    M0808Service,
)

_REQUEST_ADAPTER: Final = TypeAdapter(PublishTranscriptProteinEvidenceRequest)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "bundle",
        "explanation",
        "evidence-item",
        "assumption",
        "diagnostic",
        "reconstruction-step",
        "verification",
    }
)
app = typer.Typer(help="M08-08 transcript-protein evidence/explanation publisher.")


def _read(path: Path) -> bytes:
    try:
        body = path.read_bytes()
        strict_json_loads(body, max_bytes=M0808_MAX_CANONICAL_REQUEST_BYTES)
        return body
    except (OSError, StrictJsonError) as error:
        raise typer.BadParameter("request is not bounded strict JSON") from error


def _request_from_file(path: Path) -> PublishTranscriptProteinEvidenceRequest:
    try:
        return _REQUEST_ADAPTER.validate_json(_read(path), strict=True)
    except ValidationError as error:
        raise typer.BadParameter("request does not match the M08-08 contract") from error


@app.command("export-schema")
def export_schema(contract: Annotated[str, typer.Argument(help="M08-08 contract name.")]) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    if contract not in _CONTRACT_NAMES:
        raise typer.BadParameter("unknown M08-08 contract")
    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))  # type: ignore[arg-type]


@app.command("validate")
def validate(request: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Parse and validate one request before emitting canonical JSON."""

    typed = _request_from_file(request)
    try:
        typed = M0808Service().validate_request(typed)
    except M0808AuthorizationError as error:
        raise typer.BadParameter("M08-08 authorization denied") from error
    typer.echo(canonical_json_bytes(typed.model_dump(mode="json")).decode("utf-8"))


@app.command("publish")
def publish(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option(help="Optional new canonical result path.")] = None,
) -> None:
    """Publish one request; abstentions exit nonzero after writing the result."""

    try:
        built = M0808Service().publish(_request_from_file(request))
    except (
        M0808AuthorizationError,
        ValidationError,
        ValueError,
        TypeError,
        StrictJsonError,
    ) as error:
        raise typer.BadParameter("M08-08 publishing input is invalid") from error
    encoded = built.canonical_bytes
    if output is None:
        typer.echo(encoded.decode("utf-8"))
    else:
        if output.exists():
            raise typer.BadParameter("output already exists")
        output.write_bytes(encoded)
    if built.result.status.value != "published":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()


__all__ = ["app"]

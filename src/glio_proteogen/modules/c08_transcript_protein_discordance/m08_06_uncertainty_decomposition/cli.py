"""Typer CLI for strict M08-06 validation, decomposition, schemas, and replay."""

# CLI diagnostics collapse implementation details into stable user messages.
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

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m08_06 import (
    M0806_MAX_CANONICAL_REQUEST_BYTES,
    DecomposeTranscriptProteinUncertaintyRequest,
    TranscriptProteinUncertaintyDecompositionResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_06_uncertainty_decomposition.service import (  # noqa: E501
    M0806Service,
)

_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeTranscriptProteinUncertaintyRequest)
_RESULT_ADAPTER: Final = TypeAdapter(TranscriptProteinUncertaintyDecompositionResult)
_CONTRACT_NAMES: Final = frozenset(
    {"request", "output", "component", "decomposition", "sensitivity-envelope", "policy", "finding"}
)
app = typer.Typer(help="M08-06 uncertainty decomposition engine.")


def _read(path: Path) -> bytes:
    try:
        body = read_bounded(path, max_bytes=M0806_MAX_CANONICAL_REQUEST_BYTES)
        strict_json_loads(body, max_bytes=M0806_MAX_CANONICAL_REQUEST_BYTES)
        return body
    except (OSError, StrictJsonError) as error:
        raise typer.BadParameter("document is not bounded strict JSON") from error


def _request_from_file(path: Path) -> DecomposeTranscriptProteinUncertaintyRequest:
    try:
        return _REQUEST_ADAPTER.validate_json(_read(path), strict=True)
    except ValidationError as error:
        raise typer.BadParameter("request does not match the M08-06 contract") from error


@app.command("export-schema")
def export_schema(contract: Annotated[str, typer.Argument(help="M08-06 contract name.")]) -> None:
    """Export one strict JSON Schema 2020-12 contract."""

    if contract not in _CONTRACT_NAMES:
        raise typer.BadParameter("unknown M08-06 contract")
    typer.echo(json.dumps(contract_json_schema(contract), indent=2, sort_keys=True))  # type: ignore[arg-type]


@app.command("validate")
def validate(request: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Parse and validate one request before emitting canonical JSON."""

    typed = _request_from_file(request)
    typer.echo(canonical_json_bytes(typed.model_dump(mode="json")).decode("utf-8"))


@app.command("decompose")
def decompose(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option(help="Optional new canonical result path.")] = None,
) -> None:
    """Run the deterministic engine; safe abstention exits nonzero."""

    try:
        result = M0806Service().execute(_request_from_file(request))
    except (ValidationError, ValueError, TypeError, StrictJsonError) as error:
        raise typer.BadParameter("M08-06 decomposition input is invalid") from error
    encoded = canonical_json_bytes(result.model_dump(mode="json"))
    if output is None:
        typer.echo(encoded.decode("utf-8"))
    else:
        if output.exists():
            raise typer.BadParameter("output already exists")
        output.write_bytes(encoded)
    if result.status.value != "decomposed":
        raise typer.Exit(code=1)


@app.command("verify")
def verify(result: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Verify a result digest and deterministic replay."""

    try:
        typed = _RESULT_ADAPTER.validate_json(_read(result), strict=True)
        M0806Service().verify(typed, replay=True)
    except (ValidationError, ValueError, TypeError, StrictJsonError) as error:
        raise typer.BadParameter("M08-06 result failed replay verification") from error
    typer.echo(json.dumps({"verified": True}, sort_keys=True))


if __name__ == "__main__":
    app()


__all__ = ["app"]

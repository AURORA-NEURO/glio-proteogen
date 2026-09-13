"""Local CLI for fitted CPTAC GBM transcript--protein discordance evidence.

There is deliberately no FastAPI router in this module. Exact source terms are
not yet verified for redistribution and the aggregate artifact is trusted only
inside the invoking user's local boundary.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - Typer resolves annotations at runtime.
from typing import Annotated, Final

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    ReplayVerificationRequest,
    TranscriptProteinDiscordanceRequest,
    algorithm_profile,
    analyze_transcript_protein_discordance,
    fit_local_artifact,
    verify_transcript_protein_discordance_replay,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance.errors import (
    TranscriptProteinDiscordanceError,
)

CPTAC_GBM_DISCORDANCE_REQUEST_MAX_BYTES: Final = MAX_REQUEST_BYTES
CPTAC_GBM_DISCORDANCE_REPLAY_MAX_BYTES: Final = MAX_REPLAY_BYTES

_REQUEST_ADAPTER: Final = TypeAdapter(TranscriptProteinDiscordanceRequest)
_REPLAY_ADAPTER: Final = TypeAdapter(ReplayVerificationRequest)
_INPUT_ERROR: Final = "input does not satisfy the local discordance contract"
_FIT_ERROR: Final = "local discordance fitting failed safely"
_PROFILE_ERROR: Final = "local discordance profile is unavailable"
_QUERY_ERROR: Final = "local discordance query failed safely"
_REPLAY_ERROR: Final = "local discordance replay failed safely"

cli = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Fit and query local-only CPTAC GBM transcript--protein evidence.",
)


class TranscriptProteinDiscordanceCliError(typer.BadParameter):
    """Sanitized local discordance command failure."""


def _emit(value: object) -> None:
    typer.echo(canonical_json_bytes(value).decode("utf-8"))


def _read_typed[T](path: Path, adapter: TypeAdapter[T], max_bytes: int) -> T:
    try:
        payload = read_bounded(path, max_bytes)
        strict_json_loads(payload, max_bytes=max_bytes)
        return adapter.validate_json(payload, strict=True)
    except (OSError, RequestBodyTooLargeError, StrictJsonError, ValidationError):
        raise TranscriptProteinDiscordanceCliError(_INPUT_ERROR) from None


@cli.command("fit-local")
def cli_fit_local(
    table_s2: Annotated[Path, typer.Option(exists=True, readable=True)],
    hgnc: Annotated[Path, typer.Option(exists=True, readable=True)],
    output: Annotated[Path, typer.Option()],
    gene: Annotated[
        list[str],
        typer.Option(
            "--gene",
            help="Gene to fit; repeat for an explicit set of at most 256 genes.",
        ),
    ],
) -> None:
    """Fit only an explicit gene set from privately staged exact snapshots."""

    try:
        receipt = fit_local_artifact(
            table_s2=table_s2,
            hgnc=hgnc,
            output=output,
            gene_symbols=tuple(gene),
        )
    except (TranscriptProteinDiscordanceError, OSError, RuntimeError, ValueError):
        raise TranscriptProteinDiscordanceCliError(_FIT_ERROR) from None
    _emit(receipt)


@cli.command("profile")
def cli_profile() -> None:
    """Emit the source-bound local algorithm profile."""

    try:
        _emit(algorithm_profile())
    except (TranscriptProteinDiscordanceError, OSError, RuntimeError, ValueError):
        raise TranscriptProteinDiscordanceCliError(_PROFILE_ERROR) from None


@cli.command("analyze")
def cli_analyze(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    artifact: Annotated[Path, typer.Option(exists=True, readable=True)],
) -> None:
    """Query aggregate cohort evidence; patient measurements are not accepted."""

    typed = _read_typed(request, _REQUEST_ADAPTER, CPTAC_GBM_DISCORDANCE_REQUEST_MAX_BYTES)
    try:
        _emit(analyze_transcript_protein_discordance(typed, artifact_path=artifact))
    except (TranscriptProteinDiscordanceError, OSError, RuntimeError, ValueError):
        raise TranscriptProteinDiscordanceCliError(_QUERY_ERROR) from None


@cli.command("verify")
def cli_verify(
    envelope: Annotated[Path, typer.Argument(exists=True, readable=True)],
    artifact: Annotated[Path, typer.Option(exists=True, readable=True)],
) -> None:
    """Replay an exact query/result receipt against one local artifact."""

    typed = _read_typed(envelope, _REPLAY_ADAPTER, CPTAC_GBM_DISCORDANCE_REPLAY_MAX_BYTES)
    try:
        result = verify_transcript_protein_discordance_replay(
            typed,
            artifact_path=artifact,
        )
    except (TranscriptProteinDiscordanceError, OSError, RuntimeError, ValueError):
        raise TranscriptProteinDiscordanceCliError(_REPLAY_ERROR) from None
    _emit(result)
    if not result.verified:
        raise typer.Exit(code=1)


__all__ = [
    "CPTAC_GBM_DISCORDANCE_REPLAY_MAX_BYTES",
    "CPTAC_GBM_DISCORDANCE_REQUEST_MAX_BYTES",
    "TranscriptProteinDiscordanceCliError",
    "cli",
]

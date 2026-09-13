"""Isolated local CLI adapter for fitted CPTAC GBM cis-dosage evidence.

There is intentionally no APIRouter in this module: source terms remain
unverified and the fitted artifact is local-only.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - Typer resolves annotations at runtime.
from typing import Annotated, Final

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.research.cptac_gbm_cis_dosage import (
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    CisDosageEvidenceRequest,
    ReplayVerificationRequest,
    algorithm_profile,
    analyze_cis_dosage_evidence,
    fit_local_artifact,
    verify_cis_dosage_replay,
    verify_sources,
)
from glio_proteogen.research.cptac_gbm_cis_dosage.errors import CisDosageError

CPTAC_GBM_CIS_DOSAGE_REQUEST_MAX_BYTES: Final = MAX_REQUEST_BYTES
CPTAC_GBM_CIS_DOSAGE_REPLAY_MAX_BYTES: Final = MAX_REPLAY_BYTES

_REQUEST_ADAPTER: Final = TypeAdapter(CisDosageEvidenceRequest)
_REPLAY_ADAPTER: Final = TypeAdapter(ReplayVerificationRequest)
_INPUT_ERROR: Final = "input does not satisfy the local cis-dosage contract"
_FIT_ERROR: Final = "local cis-dosage fitting failed safely"
_PROFILE_ERROR: Final = "local cis-dosage profile is unavailable"
_QUERY_ERROR: Final = "local cis-dosage query failed safely"
_REPLAY_ERROR: Final = "local cis-dosage replay failed safely"
_SOURCE_ERROR: Final = "local source verification failed safely"

cli = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Fit and query local-only CPTAC GBM cohort cis-dosage evidence.",
)


class CisDosageCliError(typer.BadParameter):
    """Sanitized local cis-dosage command failure."""


def _emit(value: object) -> None:
    typer.echo(canonical_json_bytes(value).decode("utf-8"))


def _read_typed[T](path: Path, adapter: TypeAdapter[T], max_bytes: int) -> T:
    try:
        payload = read_bounded(path, max_bytes)
        strict_json_loads(payload, max_bytes=max_bytes)
        return adapter.validate_json(payload, strict=True)
    except (OSError, RequestBodyTooLargeError, StrictJsonError, ValidationError):
        raise CisDosageCliError(_INPUT_ERROR) from None


@cli.command("fit-local")
def cli_fit_local(
    table_s2: Annotated[Path, typer.Option(exists=True, readable=True)],
    hgnc: Annotated[Path, typer.Option(exists=True, readable=True)],
    output: Annotated[Path, typer.Option()],
    table_s3: Annotated[Path | None, typer.Option(exists=True, readable=True)] = None,
) -> None:
    """Stream exact locked sources and write a new de-identified local artifact."""

    try:
        receipt = fit_local_artifact(
            table_s2=table_s2,
            hgnc=hgnc,
            output=output,
            table_s3=table_s3,
        )
    except (CisDosageError, OSError, ValueError):
        raise CisDosageCliError(_FIT_ERROR) from None
    _emit(receipt)


@cli.command("profile")
def cli_profile() -> None:
    """Emit the source-bound local algorithm profile."""

    try:
        _emit(algorithm_profile())
    except (CisDosageError, OSError, RuntimeError, ValueError):
        raise CisDosageCliError(_PROFILE_ERROR) from None


@cli.command("analyze")
def cli_analyze(
    request: Annotated[Path, typer.Argument(exists=True, readable=True)],
    artifact: Annotated[Path, typer.Option(exists=True, readable=True)],
) -> None:
    """Query cohort-fitted gene evidence; patient measurements are not accepted."""

    typed = _read_typed(request, _REQUEST_ADAPTER, CPTAC_GBM_CIS_DOSAGE_REQUEST_MAX_BYTES)
    try:
        _emit(analyze_cis_dosage_evidence(typed, artifact_path=artifact))
    except (CisDosageError, OSError, RuntimeError, ValueError):
        raise CisDosageCliError(_QUERY_ERROR) from None


@cli.command("verify")
def cli_verify(
    envelope: Annotated[Path, typer.Argument(exists=True, readable=True)],
    artifact: Annotated[Path, typer.Option(exists=True, readable=True)],
) -> None:
    """Replay one exact query/result receipt against a local artifact."""

    typed = _read_typed(envelope, _REPLAY_ADAPTER, CPTAC_GBM_CIS_DOSAGE_REPLAY_MAX_BYTES)
    try:
        result = verify_cis_dosage_replay(typed, artifact_path=artifact)
    except (CisDosageError, OSError, RuntimeError, ValueError):
        raise CisDosageCliError(_REPLAY_ERROR) from None
    _emit(result)
    if not result.verified:
        raise typer.Exit(code=1)


@cli.command("verify-source")
def cli_verify_source(
    table_s2: Annotated[Path, typer.Option(exists=True, readable=True)],
    hgnc: Annotated[Path, typer.Option(exists=True, readable=True)],
    table_s3: Annotated[Path | None, typer.Option(exists=True, readable=True)] = None,
) -> None:
    """Verify exact local snapshot bytes without reading workbook cell values."""

    try:
        result = verify_sources(table_s2=table_s2, hgnc=hgnc, table_s3=table_s3)
    except OSError:
        raise CisDosageCliError(_SOURCE_ERROR) from None
    _emit(result)
    if not result.verified:
        raise typer.Exit(code=1)


__all__ = [
    "CPTAC_GBM_CIS_DOSAGE_REPLAY_MAX_BYTES",
    "CPTAC_GBM_CIS_DOSAGE_REQUEST_MAX_BYTES",
    "CisDosageCliError",
    "cli",
]

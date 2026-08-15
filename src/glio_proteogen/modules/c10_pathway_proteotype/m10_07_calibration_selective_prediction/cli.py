"""Typer adapter for the provisional M10-07 service boundary."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves the runtime path annotation.
from typing import Annotated, cast

import typer
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m10_07 import (
    CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M1007AuthorizationError, M1007InputError
from .service import M1007Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
_SERVICE = M1007Service()
_REQUEST_ADAPTER = TypeAdapter(CalibrateProteinRnaDiscordanceSelectivePredictionRequest)


class M1007CliError(typer.BadParameter):
    """Sanitized command-line validation error."""


def _error(message: str) -> M1007CliError:
    return M1007CliError(message)


def _read_object(path: Path) -> dict[str, object]:
    try:
        payload = strict_json_loads(path.read_bytes())
    except (OSError, StrictJsonError, ValueError) as error:
        raise _error("input must be a valid strict JSON object") from error  # noqa: TRY003
    if not isinstance(payload, dict):
        raise _error("input must be a JSON object")  # noqa: TRY003
    return cast("dict[str, object]", payload)


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise _error("output already exists; refusing to overwrite")  # noqa: TRY003
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _read_request(path: Path) -> CalibrateProteinRnaDiscordanceSelectivePredictionRequest:
    try:
        data = path.read_bytes()
        strict_json_loads(data)
        return _REQUEST_ADAPTER.validate_json(data, strict=True)
    except (OSError, StrictJsonError, ValueError, ValidationError) as error:
        raise _error("input must satisfy the strict M10-07 request contract") from error  # noqa: TRY003


@app.command("export-schema")
def export_schema(
    name: Annotated[
        str,
        typer.Argument(
            help="request, output, configuration, scope, estimate, prediction-set, or diagnostic"
        ),
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export one strict provisional contract schema."""

    names = {
        "request",
        "output",
        "configuration",
        "scope",
        "estimate",
        "prediction-set",
        "diagnostic",
    }
    if name not in names:
        raise _error("unknown M10-07 contract")  # noqa: TRY003
    data = canonical_json_bytes(contract_json_schema(name))  # type: ignore[arg-type]
    if output is None:
        typer.echo(data.decode("utf-8"))
    else:
        _write_new(output, data)


@app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    """Validate one request without executing it."""

    try:
        request = _SERVICE.validate_request(_read_request(path))
    except (ValidationError, ValueError, M1007AuthorizationError) as error:
        raise _error("request does not satisfy the M10-07 contract") from error  # noqa: TRY003
    typer.echo(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


@app.command("calibrate")
def calibrate(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Run calibration and emit canonical replay bytes."""

    try:
        built = _SERVICE.execute(_read_request(path))
    except (ValidationError, ValueError, M1007AuthorizationError, M1007InputError) as error:
        raise _error("request was rejected by the M10-07 service") from error  # noqa: TRY003
    if output is None:
        typer.echo(built.canonical_bytes.decode("utf-8"))
    else:
        _write_new(output, built.canonical_bytes)
    if built.result.human_review_required:
        raise typer.Exit(code=1)


@app.command("verify")
def verify(
    result_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    canonical_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Verify a result against canonical replay bytes."""

    result = _read_object(result_path)
    try:
        replay = _SERVICE.verify(result, canonical_path.read_bytes())
    except (OSError, TypeError, ValueError, ValidationError, StrictJsonError) as error:
        raise _error("replay input is invalid") from error  # noqa: TRY003
    typer.echo(
        json.dumps(
            {
                "verified": replay.verified,
                "reason": replay.reason,
                "result_digest": replay.result_digest,
            },
            sort_keys=True,
        )
    )
    if not replay.verified:
        raise typer.Exit(code=1)


__all__ = ["app"]

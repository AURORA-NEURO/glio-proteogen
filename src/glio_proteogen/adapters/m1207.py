"""Standalone FastAPI and Typer adapters for provisional M12-07."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - Typer resolves Path at runtime.
from typing import Annotated, Final

import typer
from fastapi import FastAPI, HTTPException
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestSizeLimitMiddleware, read_bounded
from glio_proteogen.contracts.m12_07 import (
    M1207_MAX_CANONICAL_REQUEST_BYTES,
    M1207_MAX_CANONICAL_RESULT_BYTES,
    AdjudicateBiomarkerPanelPlausibilityRequest,
    BiomarkerPanelPlausibilityAdjudicationResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c12_driver_protein_consequence import (
    m12_07_plausibility_adjudicator as m1207,
)

_REQUEST_ADAPTER: Final = TypeAdapter(AdjudicateBiomarkerPanelPlausibilityRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelPlausibilityAdjudicationResult)
_JSON_OBJECT_ADAPTER: Final = TypeAdapter(dict[str, object])

app = FastAPI(title="GLIO-PROTEOGEN M12-07", version="0.1.0-provisional")
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=M1207_MAX_CANONICAL_REQUEST_BYTES,
    result_max_bytes=M1207_MAX_CANONICAL_RESULT_BYTES,
)
m1207_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _safe_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, m1207.M1207PlausibilityAuthorizationError):
        return HTTPException(status_code=403, detail="M12-07 upstream authorization denied")
    return HTTPException(status_code=422, detail="invalid M12-07 request or result")


def _strict_object(value: object, *, max_bytes: int) -> dict[str, object]:
    candidate = _JSON_OBJECT_ADAPTER.validate_python(value, strict=True)
    raw = canonical_json_bytes(candidate)
    decoded = strict_json_loads(raw, max_bytes=max_bytes)
    return _JSON_OBJECT_ADAPTER.validate_python(decoded, strict=True)


def _request_from_object(value: object) -> AdjudicateBiomarkerPanelPlausibilityRequest:
    decoded = _strict_object(value, max_bytes=M1207_MAX_CANONICAL_REQUEST_BYTES)
    m1207.preflight_m1207_authorization(decoded)
    return _REQUEST_ADAPTER.validate_json(
        canonical_json_bytes(decoded),
        strict=True,
    )


@app.get("/v1/m12-07/schema/{name}")
def export_schema(name: str) -> dict[str, object]:
    try:
        return contract_json_schema(name)  # type: ignore[arg-type]
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="unknown M12-07 schema") from exc


@app.post("/v1/modules/M12-07/adjudicate")
def adjudicate(body: dict[str, object]) -> dict[str, object]:
    try:
        request = _request_from_object(body)
        result = m1207.M1207Service().execute(request)
        return result.model_dump(mode="json")
    except (ValidationError, ValueError, TypeError) as exc:
        raise _safe_http_error(exc) from exc


@app.post("/v1/modules/M12-07/verify")
def verify(body: dict[str, object]) -> dict[str, object]:
    try:
        envelope = _strict_object(body, max_bytes=M1207_MAX_CANONICAL_RESULT_BYTES)
        if set(envelope) != {"request", "result"}:
            raise ValueError(  # noqa: TRY003, TRY301
                "verify envelope must contain request and result only"
            )
        request = _request_from_object(envelope["request"])
        result_object = _strict_object(
            envelope["result"], max_bytes=M1207_MAX_CANONICAL_RESULT_BYTES
        )
        result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(result_object), strict=True)
        verified = m1207.M1207Service().verify(request, result)
        return verified.model_dump(mode="json")
    except (ValidationError, ValueError, TypeError) as exc:
        raise _safe_http_error(exc) from exc


def _load_json(path: Path, *, max_bytes: int) -> dict[str, object]:
    if not path.is_file():
        raise typer.BadParameter(  # noqa: TRY003
            "input path must name a regular JSON file"
        )
    try:
        decoded = strict_json_loads(read_bounded(path, max_bytes), max_bytes=max_bytes)
        return _JSON_OBJECT_ADAPTER.validate_python(decoded, strict=True)
    except (OSError, ValueError, TypeError, ValidationError) as exc:
        raise typer.BadParameter(  # noqa: TRY003
            "input is not a valid strict JSON object"
        ) from exc


def _echo(value: object) -> None:
    typer.echo(canonical_json_bytes(value).decode("utf-8"))


@m1207_app.command("export-schema")
def export_schema_cli(
    name: Annotated[
        str, typer.Argument(help="request, output, control, evaluation, conflict or finding")
    ],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    try:
        schema = contract_json_schema(name)  # type: ignore[arg-type]
    except (KeyError, ValueError) as exc:
        raise typer.BadParameter("unknown M12-07 schema") from exc  # noqa: TRY003
    encoded = canonical_json_bytes(schema)
    if output is None:
        typer.echo(encoded.decode("utf-8"))
        return
    if output.exists():
        raise typer.BadParameter("refusing to overwrite existing output")  # noqa: TRY003
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(encoded)
    except OSError as exc:
        raise typer.BadParameter("could not write schema output") from exc  # noqa: TRY003


@m1207_app.command("adjudicate")
def adjudicate_cli(
    request: Annotated[Path, typer.Argument(help="strict JSON request path")],
) -> None:
    try:
        parsed = _load_json(request, max_bytes=M1207_MAX_CANONICAL_REQUEST_BYTES)
        _echo(m1207.M1207Service().execute(_request_from_object(parsed)).model_dump(mode="json"))
    except (typer.BadParameter, ValidationError, ValueError, TypeError) as exc:
        if isinstance(exc, typer.BadParameter):
            raise
        raise typer.BadParameter("M12-07 request was rejected") from exc  # noqa: TRY003


@m1207_app.command("verify")
def verify_cli(
    request: Annotated[Path, typer.Argument(help="strict JSON request path")],
    result: Annotated[Path, typer.Argument(help="strict JSON result path")],
) -> None:
    try:
        request_object = _load_json(request, max_bytes=M1207_MAX_CANONICAL_REQUEST_BYTES)
        result_object = _load_json(result, max_bytes=M1207_MAX_CANONICAL_RESULT_BYTES)
        request_model = _request_from_object(request_object)
        result_model = _RESULT_ADAPTER.validate_json(
            canonical_json_bytes(result_object), strict=True
        )
        _echo(m1207.M1207Service().verify(request_model, result_model).model_dump(mode="json"))
    except (typer.BadParameter, ValidationError, ValueError, TypeError) as exc:
        if isinstance(exc, typer.BadParameter):
            raise
        raise typer.BadParameter(  # noqa: TRY003
            "M12-07 result verification failed"
        ) from exc


__all__ = ["app", "export_schema", "m1207_app"]

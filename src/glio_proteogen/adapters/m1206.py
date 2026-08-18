"""Standalone FastAPI and Typer adapters for provisional M12-06."""

# Typer's public function signatures intentionally use boolean flags and Path
# annotations; adapter error messages are sanitized at the boundary.
# ruff: noqa: TC003,TRY003,TRY004,TRY301,FBT002,E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Final, cast

import typer
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import read_bounded
from glio_proteogen.contracts.m12_06 import (
    M1206_MAX_CANONICAL_REQUEST_BYTES,
    M1206_MAX_CANONICAL_RESULT_BYTES,
    BiomarkerPanelPerturbationSensitivityResult,
    SimulateBiomarkerPanelPerturbationRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c11_protein_native_subtype.m12_06_perturbation_sensitivity_simulator.engine import (
    M1206AuthorizationError,
    M1206ReplayError,
    preflight_m1206_authorization,
)
from glio_proteogen.modules.c11_protein_native_subtype.m12_06_perturbation_sensitivity_simulator.service import (
    M1206Service,
)

_REQUEST_ADAPTER: Final = TypeAdapter(SimulateBiomarkerPanelPerturbationRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelPerturbationSensitivityResult)
_SERVICE: Final = M1206Service()
_SCHEMA_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "scenario",
        "response",
        "sensitivity-surface",
        "configuration",
        "policy",
        "finding",
    }
)


def _validated_request(
    payload: bytes,
    *,
    max_bytes: int = M1206_MAX_CANONICAL_REQUEST_BYTES,
) -> SimulateBiomarkerPanelPerturbationRequest:
    try:
        decoded = strict_json_loads(payload, max_bytes=max_bytes)
        preflight_m1206_authorization(decoded)
        return _REQUEST_ADAPTER.validate_json(payload, strict=True)
    except M1206AuthorizationError:
        raise
    except StrictJsonError:
        raise
    except ValidationError as error:
        raise ValueError(sanitized_validation_errors(error)) from error


def _json_model(value: object) -> dict[str, object]:
    return cast("dict[str, object]", cast("BaseModel", value).model_dump(mode="json"))


app = FastAPI(title="GLIO-PROTEOGEN M12-06", version="0.1.0-provisional")


@app.get("/v1/m12-06/schema/{name}")
async def export_schema(name: str) -> dict[str, object]:
    if name not in _SCHEMA_NAMES:
        raise HTTPException(status_code=404, detail="unknown M12-06 schema")
    return contract_json_schema(name)  # type: ignore[arg-type]


@app.post("/v1/modules/M12-06/simulate")
async def simulate(request: Request) -> JSONResponse:
    body = await request.body()
    try:
        validated = _validated_request(body)
        result = _SERVICE.execute(validated)
    except M1206AuthorizationError as error:
        raise HTTPException(
            status_code=403, detail="M12-06 controls do not authorize this operation"
        ) from error
    except StrictJsonError as error:
        raise HTTPException(status_code=400, detail=strict_json_error_detail(error)) from error
    except (ValidationError, ValueError) as error:
        raise HTTPException(
            status_code=422, detail="request does not match the declared contract"
        ) from error
    return JSONResponse(_json_model(result))


@app.post("/v1/modules/M12-06/verify")
async def verify(request: Request) -> JSONResponse:
    body = await request.body()
    try:
        decoded = strict_json_loads(body, max_bytes=M1206_MAX_CANONICAL_RESULT_BYTES)
        if not isinstance(decoded, dict):
            raise ValueError("verify envelope must be an object")
        preflight_m1206_authorization(decoded.get("request"))
        typed_request = _REQUEST_ADAPTER.validate_json(
            json.dumps(decoded.get("request"), separators=(",", ":")), strict=True
        )
        typed_result = _RESULT_ADAPTER.validate_json(
            json.dumps(decoded.get("result"), separators=(",", ":")), strict=True
        )
        checked = _SERVICE.verify(typed_request, typed_result)
    except M1206ReplayError as error:
        raise HTTPException(status_code=409, detail="M12-06 replay verification failed") from error
    except M1206AuthorizationError as error:
        raise HTTPException(
            status_code=403, detail="M12-06 controls do not authorize this operation"
        ) from error
    except StrictJsonError as error:
        raise HTTPException(status_code=400, detail=strict_json_error_detail(error)) from error
    except (ValidationError, ValueError) as error:
        raise HTTPException(
            status_code=422, detail="request does not match the declared contract"
        ) from error
    return JSONResponse(_json_model(checked))


m1206_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def _read_json(
    path: Path,
    max_bytes: int = M1206_MAX_CANONICAL_REQUEST_BYTES,
) -> bytes:
    return read_bounded(path, max_bytes)


def _write_json(path: Path, value: object, *, force: bool) -> None:
    if path.exists() and not force:
        raise typer.BadParameter("output already exists; pass --force to overwrite")
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


@m1206_app.command("export-schema")
def export_schema_cli(
    name: Annotated[str, typer.Argument()],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    if name not in _SCHEMA_NAMES:
        raise typer.BadParameter("unknown M12-06 schema", param_hint="name")
    payload = contract_json_schema(name)  # type: ignore[arg-type]
    if output is None:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _write_json(output, payload, force=force)


@m1206_app.command("simulate")
def simulate_cli(
    request: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    try:
        result = _SERVICE.execute(_validated_request(_read_json(request)))
    except (StrictJsonError, M1206AuthorizationError, ValidationError, ValueError) as error:
        raise typer.BadParameter("request does not match the declared contract") from error
    payload = _json_model(result)
    if output is None:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _write_json(output, payload, force=force)


@m1206_app.command("verify")
def verify_cli(
    request: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    result: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    try:
        typed_request = _validated_request(_read_json(request))
        result_bytes = _read_json(result, M1206_MAX_CANONICAL_RESULT_BYTES)
        strict_json_loads(result_bytes, max_bytes=M1206_MAX_CANONICAL_RESULT_BYTES)
        typed_result = _RESULT_ADAPTER.validate_json(result_bytes, strict=True)
        _SERVICE.verify(typed_request, typed_result)
    except (
        StrictJsonError,
        M1206AuthorizationError,
        M1206ReplayError,
        ValidationError,
        ValueError,
    ) as error:
        raise typer.BadParameter("M12-06 replay verification failed") from error
    typer.echo("verified")


__all__ = ["app", "m1206_app"]

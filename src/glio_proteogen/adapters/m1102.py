"""Strict FastAPI and Typer adapters for provisional M11-02."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Literal

import typer
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import TypeAdapter, ValidationError

if __package__ in {None, ""}:
    _SOURCE_ROOT = Path(__file__).resolve().parents[2]
    if str(_SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SOURCE_ROOT))

from glio_proteogen.adapters.limits import (
    RequestBodyTooLargeError,
    RequestSizeLimitMiddleware,
    read_bounded,
)
from glio_proteogen.contracts.m11_02 import (
    M1102_MAX_CANONICAL_REQUEST_BYTES,
    M1102_MAX_CANONICAL_RESULT_BYTES,
    StratifyVariantPeptideContextRequest,
    VariantPeptideContextStratificationResult,
    canonical_request_digest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c11_protein_native_subtype.m11_02_context_subtype_stratifier import (
    M1102AuthorizationError,
    M1102Service,
)

_REQUEST_ADAPTER = TypeAdapter(StratifyVariantPeptideContextRequest)
_RESULT_ADAPTER = TypeAdapter(VariantPeptideContextStratificationResult)


def _request_json(body: bytes) -> object:
    return strict_json_loads(body, max_bytes=M1102_MAX_CANONICAL_REQUEST_BYTES)


def _error_response(
    detail: list[dict[str, object]],
    *,
    status_code: int = 422,
) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _request_too_large() -> JSONResponse:
    return _error_response(
        [
            {
                "type": "request_too_large",
                "loc": (),
                "msg": "request body exceeds the byte limit",
            }
        ],
        status_code=413,
    )


def _canonical_response(value: object) -> Response:
    return Response(content=canonical_json_bytes(value), media_type="application/json")


def create_m1102_app(service: M1102Service | None = None) -> FastAPI:  # noqa: C901
    """Create an isolated API with strict raw-body parsing and sanitized errors."""

    active = service or M1102Service()
    api = FastAPI(title="GLIO-PROTEOGEN M11-02", version="0.1.0-provisional")
    api.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=M1102_MAX_CANONICAL_RESULT_BYTES,
    )

    @api.post("/v1/m11-02/schema/{contract}")
    async def export_schema(
        contract: Literal[
            "request",
            "output",
            "observation",
            "profile",
            "policy",
            "rule",
            "mechanism-applicability",
            "diagnostic",
        ],
    ) -> JSONResponse:
        return JSONResponse(content=contract_json_schema(contract))

    @api.post("/v1/m11-02/validate")
    async def validate(request: Request) -> JSONResponse:
        try:
            body = await request.body()
            typed = active.validate_json(body)
        except RequestBodyTooLargeError:
            return _request_too_large()
        except StrictJsonError as error:
            return _error_response([strict_json_error_detail(error)])
        except ValidationError as error:
            return _error_response(sanitized_validation_errors(error))
        except M1102AuthorizationError as error:
            return _error_response(
                [{"type": "authorization_denied", "loc": (), "msg": str(error)}],
                status_code=403,
            )
        return JSONResponse(
            content={"valid": True, "request_digest": canonical_request_digest(typed)}
        )

    @api.post("/v1/m11-02/stratify")
    async def stratify(request: Request) -> Response:
        try:
            body = await request.body()
            typed = active.validate_json(body)
            result = active.execute(typed)
        except RequestBodyTooLargeError:
            return _request_too_large()
        except StrictJsonError as error:
            return _error_response([strict_json_error_detail(error)])
        except ValidationError as error:
            return _error_response(sanitized_validation_errors(error))
        except M1102AuthorizationError as error:
            return _error_response(
                [{"type": "authorization_denied", "loc": (), "msg": str(error)}],
                status_code=403,
            )
        return _canonical_response(result)

    @api.post("/v1/m11-02/verify")
    async def verify(request: Request) -> Response:
        try:
            body = await request.body()
            parsed = _request_json(body)
            result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
            verified = active.verify(result)
        except RequestBodyTooLargeError:
            return _request_too_large()
        except StrictJsonError as error:
            return _error_response([strict_json_error_detail(error)])
        except ValidationError as error:
            return _error_response(sanitized_validation_errors(error))
        except (M1102AuthorizationError, ValueError) as error:
            return _error_response(
                [{"type": "verification_failed", "loc": (), "msg": str(error)}],
                status_code=422,
            )
        return _canonical_response(verified)

    return api


m1102_api = create_m1102_app()
m1102_app = typer.Typer(
    name="m11-02",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Provisional M11-02 context and subtype stratification.",
)


def _read_argument(value: str, max_bytes: int = M1102_MAX_CANONICAL_REQUEST_BYTES) -> bytes:
    path = Path(value)
    if path.is_file():
        return read_bounded(path, max_bytes)
    return value.encode("utf-8")


def _parse_argument(value: str, max_bytes: int = M1102_MAX_CANONICAL_REQUEST_BYTES) -> object:
    return strict_json_loads(_read_argument(value, max_bytes), max_bytes=max_bytes)


def _emit(value: object) -> None:
    typer.echo(canonical_json_bytes(value).decode("utf-8"))


@m1102_app.command("export-schema")
def export_schema_cli(
    contract: Annotated[
        Literal[
            "request",
            "output",
            "observation",
            "profile",
            "policy",
            "rule",
            "mechanism-applicability",
            "diagnostic",
        ],
        typer.Argument(help="M11-02 contract to export as JSON Schema 2020-12."),
    ],
) -> None:
    _emit(contract_json_schema(contract))


@m1102_app.command("validate")
def validate_cli(
    request: Annotated[str, typer.Argument(help="JSON text or path to a request.")],
) -> None:
    try:
        typed = M1102Service().validate_json(_read_argument(request))
    except StrictJsonError as error:
        typer.echo(json.dumps({"detail": [strict_json_error_detail(error)]}), err=True)
        raise typer.Exit(code=2) from error
    except ValidationError as error:
        typer.echo(json.dumps({"detail": sanitized_validation_errors(error)}), err=True)
        raise typer.Exit(code=2) from error
    except M1102AuthorizationError as error:
        typer.echo(
            json.dumps({"detail": [{"type": "authorization_denied", "msg": str(error)}]}), err=True
        )
        raise typer.Exit(code=2) from error
    _emit({"valid": True, "request_digest": canonical_request_digest(typed)})


@m1102_app.command("stratify")
def stratify_cli(
    request: Annotated[str, typer.Argument(help="JSON text or path to a request.")],
) -> None:
    try:
        typed = M1102Service().validate_json(_read_argument(request))
        _emit(M1102Service().execute(typed))
    except (StrictJsonError, ValidationError, M1102AuthorizationError, ValueError) as error:
        typer.echo(json.dumps({"detail": str(error)}), err=True)
        raise typer.Exit(code=1) from error


@m1102_app.command("verify")
def verify_cli(result: Annotated[str, typer.Argument(help="JSON result text or path.")]) -> None:
    try:
        parsed = _parse_argument(result, M1102_MAX_CANONICAL_RESULT_BYTES)
        typed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(parsed), strict=True)
        _emit(M1102Service().verify(typed))
    except (StrictJsonError, ValidationError, M1102AuthorizationError, ValueError) as error:
        typer.echo(json.dumps({"detail": str(error)}), err=True)
        raise typer.Exit(code=1) from error


if __name__ == "__main__":
    m1102_app()


__all__ = ["create_m1102_app", "m1102_api", "m1102_app"]

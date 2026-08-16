"""FastAPI interface for strict M09-08 validation and publication."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_08 import (
    M0908_MAX_CANONICAL_REQUEST_BYTES,
    PublishComplexActivityEvidenceRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)

from .engine import M0908AuthorizationError, M0908InputError
from .service import M0908Service

_REQUEST_ADAPTER: Final = TypeAdapter(PublishComplexActivityEvidenceRequest)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "evidence-bundle",
        "explanation",
        "source",
        "assumption",
        "counter-evidence",
        "diagnostic",
        "reconstruction-step",
        "verification",
    }
)


def _validation_error(error: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=sanitized_validation_errors(error))


async def _strict_body(request: Request) -> bytes:
    body = await request.body()
    try:
        strict_json_loads(body, max_bytes=M0908_MAX_CANONICAL_REQUEST_BYTES)
    except StrictJsonError as error:
        raise HTTPException(status_code=422, detail=strict_json_error_detail(error)) from error
    return body


def create_app(service: M0908Service | None = None) -> FastAPI:
    """Create an isolated API with no persistence or external-content traversal."""

    publisher_service = service or M0908Service()
    app = FastAPI(title="GLIO Proteogen M09-08", version="0.1.0-provisional")

    @app.get("/v1/modules/M09-08/schemas/{contract}")
    def export_schema(contract: str) -> dict[str, object]:
        if contract not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M09-08 contract")
        return contract_json_schema(contract)  # type: ignore[arg-type]

    @app.post("/v1/modules/M09-08/validate")
    async def validate_request(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = publisher_service.validate_request(
                _REQUEST_ADAPTER.validate_json(body, strict=True)
            )
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0908AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M09-08 authorization denied") from error
        return JSONResponse(content=typed.model_dump(mode="json"))

    @app.post("/v1/modules/M09-08/publish")
    async def publish(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = publisher_service.validate_request(
                _REQUEST_ADAPTER.validate_json(body, strict=True)
            )
            built = publisher_service.publish(typed)
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0908AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M09-08 authorization denied") from error
        return JSONResponse(
            content={
                "result": built.result.model_dump(mode="json"),
                "canonical": built.canonical_bytes.decode("utf-8"),
            }
        )

    @app.exception_handler(M0908InputError)
    async def input_error(_request: Request, _error: M0908InputError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "M09-08 input rejected"})

    return app


app = create_app()

__all__ = ["app", "create_app"]

"""FastAPI interface for strict M09-03 validation and estimation."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_03 import (
    M0903_MAX_CANONICAL_REQUEST_BYTES,
    EstimateComplexActivityBaselineRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)

from .engine import M0903AuthorizationError, M0903InputError
from .service import M0903Service

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateComplexActivityBaselineRequest)
_CONTRACT_NAMES: Final = frozenset({"request", "output", "configuration", "estimate", "diagnostic"})


async def _strict_body(request: Request) -> bytes:
    body = await request.body()
    try:
        strict_json_loads(body, max_bytes=M0903_MAX_CANONICAL_REQUEST_BYTES)
    except StrictJsonError as error:
        raise HTTPException(status_code=422, detail=strict_json_error_detail(error)) from error
    return body


def _validation_error(error: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=sanitized_validation_errors(error))


def create_app(service: M0903Service | None = None) -> FastAPI:
    """Create an isolated API app so callers can inject a controlled service."""

    estimator = service or M0903Service()
    app = FastAPI(title="GLIO Proteogen M09-03", version="0.1.0-provisional")

    @app.get("/v1/modules/M09-03/schemas/{contract}")
    def export_schema(contract: str) -> dict[str, object]:
        if contract not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M09-03 contract")
        return contract_json_schema(contract)  # type: ignore[arg-type]

    @app.post("/v1/modules/M09-03/validate")
    async def validate_request(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = estimator.validate_request(_REQUEST_ADAPTER.validate_json(body, strict=True))
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0903AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M09-03 authorization denied") from error
        return JSONResponse(content=typed.model_dump(mode="json"))

    @app.post("/v1/modules/M09-03/estimate")
    async def estimate(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = estimator.validate_request(_REQUEST_ADAPTER.validate_json(body, strict=True))
            built = estimator.construct(typed)
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0903AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M09-03 authorization denied") from error
        return JSONResponse(
            content={
                "result": built.result.model_dump(mode="json"),
                "canonical": built.canonical_bytes.decode("utf-8"),
            }
        )

    @app.exception_handler(M0903InputError)
    async def input_error(_request: Request, _error: M0903InputError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "M09-03 input rejected"})

    return app


app = create_app()

__all__ = ["app", "create_app"]

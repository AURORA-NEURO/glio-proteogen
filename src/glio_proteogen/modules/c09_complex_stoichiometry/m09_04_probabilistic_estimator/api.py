"""FastAPI surface for strict M09-04 validation, estimation, and replay."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_04 import (
    M0904_MAX_CANONICAL_REQUEST_BYTES,
    EstimateComplexActivityProbabilisticRequest,
    EstimateComplexActivityProbabilisticResult,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)

from .engine import M0904AuthorizationError, M0904InputError
from .service import M0904Service

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateComplexActivityProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(EstimateComplexActivityProbabilisticResult)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "posterior",
        "diagnostic",
        "prior",
        "constraint",
        "configuration",
        "verification",
    }
)


async def _strict_body(request: Request, *, max_bytes: int) -> bytes:
    body = await request.body()
    try:
        strict_json_loads(body, max_bytes=max_bytes)
    except StrictJsonError as error:
        raise HTTPException(status_code=422, detail=strict_json_error_detail(error)) from error
    return body


def _validation_error(error: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=sanitized_validation_errors(error))


def create_app(service: M0904Service | None = None) -> FastAPI:  # noqa: C901 - isolated route wiring
    """Create an isolated API with no persistence or external content traversal."""

    integration_service = service or M0904Service()
    app = FastAPI(title="GLIO Proteogen M09-04", version="0.1.0-provisional")

    @app.get("/v1/modules/M09-04/schemas/{contract}")
    def export_schema(contract: str) -> dict[str, object]:
        if contract not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M09-04 contract")
        return contract_json_schema(contract)  # type: ignore[arg-type]

    @app.post("/v1/modules/M09-04/validate")
    async def validate_request(request: Request) -> JSONResponse:
        body = await _strict_body(request, max_bytes=M0904_MAX_CANONICAL_REQUEST_BYTES)
        try:
            typed = integration_service.validate_request(
                _REQUEST_ADAPTER.validate_json(body, strict=True)
            )
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0904AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M09-04 authorization denied") from error
        return JSONResponse(content=typed.model_dump(mode="json"))

    @app.post("/v1/modules/M09-04/estimate")
    async def estimate(request: Request) -> JSONResponse:
        body = await _strict_body(request, max_bytes=M0904_MAX_CANONICAL_REQUEST_BYTES)
        try:
            typed = integration_service.validate_request(
                _REQUEST_ADAPTER.validate_json(body, strict=True)
            )
            built = integration_service.build(typed)
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0904AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M09-04 authorization denied") from error
        except M0904InputError as error:
            raise HTTPException(status_code=422, detail="M09-04 result rejected") from error
        return JSONResponse(
            content={
                "result": built.result.model_dump(mode="json"),
                "canonical": built.canonical_bytes.decode("utf-8"),
            }
        )

    @app.post("/v1/modules/M09-04/verify")
    async def verify(request: Request) -> JSONResponse:
        body = await _strict_body(request, max_bytes=M0904_MAX_CANONICAL_REQUEST_BYTES)
        try:
            typed = _RESULT_ADAPTER.validate_json(body, strict=True)
        except ValidationError as error:
            raise _validation_error(error) from error
        return JSONResponse(content=integration_service.verify(typed).model_dump(mode="json"))

    return app


app = create_app()

__all__ = ["app", "create_app"]

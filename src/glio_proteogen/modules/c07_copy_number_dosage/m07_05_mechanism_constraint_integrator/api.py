"""FastAPI surface for provisional M07-05 constraint integration."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m07_05 import (
    M0705_MAX_CANONICAL_REQUEST_BYTES,
    IntegrateProteotypeConstraintsRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)

from .engine import ConstraintAuthorizationError, ConstraintInputError
from .service import M0705Service

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateProteotypeConstraintsRequest)
_CONTRACT_NAMES: Final = frozenset(
    {"request", "output", "constraint", "constraint-set", "evaluation", "ablation", "estimate"}
)


def _validation_error(error: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=sanitized_validation_errors(error))


async def _strict_body(request: Request) -> bytes:
    body = await request.body()
    try:
        strict_json_loads(body, max_bytes=M0705_MAX_CANONICAL_REQUEST_BYTES)
    except StrictJsonError as error:
        raise HTTPException(status_code=422, detail=strict_json_error_detail(error)) from error
    return body


def create_app(service: M0705Service | None = None) -> FastAPI:
    """Create an isolated API app with no persistence or model side effects."""

    integration_service = service or M0705Service()
    app = FastAPI(title="GLIO Proteogen M07-05", version="0.1.0-provisional")

    @app.get("/v1/modules/M07-05/schemas/{contract}")
    def export_schema(contract: str) -> dict[str, object]:
        if contract not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M07-05 contract")
        return contract_json_schema(contract)  # type: ignore[arg-type]

    @app.post("/v1/modules/M07-05/validate")
    async def validate_request(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = integration_service.validate_request(
                _REQUEST_ADAPTER.validate_json(body, strict=True)
            )
        except ValidationError as error:
            raise _validation_error(error) from error
        except ConstraintAuthorizationError as error:
            raise HTTPException(status_code=403, detail="M07-05 authorization denied") from error
        return JSONResponse(content=typed.model_dump(mode="json"))

    @app.post("/v1/modules/M07-05/integrate")
    async def integrate(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = integration_service.validate_request(
                _REQUEST_ADAPTER.validate_json(body, strict=True)
            )
            built = integration_service.integrate(typed)
        except ValidationError as error:
            raise _validation_error(error) from error
        except ConstraintAuthorizationError as error:
            raise HTTPException(status_code=403, detail="M07-05 authorization denied") from error
        return JSONResponse(
            content={
                "result": built.result.model_dump(mode="json"),
                "canonical": built.canonical_bytes.decode("utf-8"),
            }
        )

    @app.exception_handler(ConstraintInputError)
    async def constraint_input_error(
        _request: Request,
        _error: ConstraintInputError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "M07-05 input rejected"})

    return app


app = create_app()

__all__ = ["app", "create_app"]

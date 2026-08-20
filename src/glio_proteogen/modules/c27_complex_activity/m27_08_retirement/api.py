"""FastAPI routes for strict M27-08 validation, retirement and replay."""

# Route closures intentionally keep the complete module surface together.
# ruff: noqa: C901, TRY003, TRY004, TRY301

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from glio_proteogen.contracts.m27_08 import (
    M2708_MAX_CANONICAL_REQUEST_BYTES,
    M2708_MAX_CANONICAL_RESULT_BYTES,
    ComplexActivityRetirementResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c27_complex_activity.m27_08_retirement.service import M2708Service


def create_app() -> FastAPI:
    api = FastAPI(title="GLIO-PROTEOGEN M27-08")
    service = M2708Service()

    @api.get("/v1/contracts/M27-08/schema")
    def schemas() -> dict[str, dict[str, object]]:
        return {str(key): value for key, value in contract_json_schemas().items()}

    @api.get("/v1/contracts/M27-08/{name}/schema")
    def schema(name: str) -> dict[str, object]:
        if name not in contract_json_schemas():
            raise HTTPException(status_code=404, detail="schema not found")
        return contract_json_schema(name)

    async def body(request: Request, *, max_bytes: int) -> dict[str, Any]:
        try:
            raw = await request.body()
            value = strict_json_loads(raw, max_bytes=max_bytes)
            if not isinstance(value, dict):
                raise ValueError("object required")
            return dict(value)
        except (StrictJsonError, ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="request validation failed") from error

    @api.post("/v1/modules/M27-08/validate")
    async def validate(request: Request) -> JSONResponse:
        try:
            parsed = service.validate_request(
                await body(request, max_bytes=M2708_MAX_CANONICAL_REQUEST_BYTES)
            )
            return JSONResponse(parsed.model_dump(mode="json"))
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=422, detail="request validation failed") from error

    @api.post("/v1/modules/M27-08/retire")
    async def retire(request: Request) -> JSONResponse:
        try:
            result = service.execute(
                service.validate_request(
                    await body(request, max_bytes=M2708_MAX_CANONICAL_REQUEST_BYTES)
                )
            )
            return JSONResponse(result.model_dump(mode="json"))
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=422, detail="retirement denied or invalid") from error

    @api.post("/v1/modules/M27-08/verify")
    async def verify(request: Request) -> JSONResponse:
        try:
            value = await body(request, max_bytes=M2708_MAX_CANONICAL_RESULT_BYTES)
            result = ComplexActivityRetirementResult.model_validate(value, strict=True)
            return JSONResponse({"verified": service.verify(result)})
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="result verification failed") from error

    return api


app = create_app()

__all__ = ["app", "create_app"]

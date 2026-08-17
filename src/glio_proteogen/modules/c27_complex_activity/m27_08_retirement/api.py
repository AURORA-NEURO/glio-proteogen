"""FastAPI routes for strict M27-08 validation, retirement and replay."""

# Route closures intentionally keep the complete module surface together.
# ruff: noqa: C901, TRY003, TRY004, TRY301, TRY300

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from glio_proteogen.contracts.m27_08 import (
    ComplexActivityRetirementResult,
    contract_json_schema,
    contract_json_schemas,
)
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

    async def body(request: Request) -> dict[str, Any]:
        try:
            raw = await request.body()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("object required")
            return value
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=422, detail="request validation failed") from error

    @api.post("/v1/modules/M27-08/validate")
    async def validate(request: Request) -> JSONResponse:
        try:
            parsed = service.validate_request(await body(request))
            return JSONResponse(parsed.model_dump(mode="json"))
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=422, detail="request validation failed") from error

    @api.post("/v1/modules/M27-08/retire")
    async def retire(request: Request) -> JSONResponse:
        try:
            result = service.execute(service.validate_request(await body(request)))
            return JSONResponse(result.model_dump(mode="json"))
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=422, detail="retirement denied or invalid") from error

    @api.post("/v1/modules/M27-08/verify")
    async def verify(request: Request) -> JSONResponse:
        try:
            result = ComplexActivityRetirementResult.model_validate_json(
                await request.body(), strict=True
            )
            return JSONResponse({"verified": service.verify(result)})
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="result verification failed") from error

    return api


app = create_app()

__all__ = ["app", "create_app"]

"""FastAPI schema, validation, execution, and verification routes."""

# ruff: noqa: C901, TRY003, TRY004, TRY300, TRY301

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from glio_proteogen.contracts.m27_07 import (
    ComplexActivityChangeControlResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control.service import M2707Service


def create_app() -> FastAPI:
    api = FastAPI(title="GLIO-PROTEOGEN M27-07")
    service = M2707Service()

    @api.get("/v1/contracts/M27-07/schema")
    def schemas() -> dict[str, dict[str, object]]:
        return {str(key): value for key, value in contract_json_schemas().items()}

    @api.get("/v1/contracts/M27-07/{name}/schema")
    def schema(name: str) -> dict[str, object]:
        if name not in contract_json_schemas():
            raise HTTPException(status_code=404, detail="schema not found")
        return contract_json_schema(name)

    async def _body(request: Request) -> dict[str, Any]:
        try:
            raw = await request.body()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("object required")
            return value
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=422, detail="request validation failed") from error

    @api.post("/v1/modules/M27-07/validate")
    async def validate(request: Request) -> JSONResponse:
        try:
            value = await _body(request)
            parsed = service.validate_request(value)
            return JSONResponse(parsed.model_dump(mode="json"))
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=422, detail="request validation failed") from error

    @api.post("/v1/modules/M27-07/control")
    async def control(request: Request) -> JSONResponse:
        try:
            value = await _body(request)
            parsed = service.validate_request(value)
            result = service.execute(parsed)
            return JSONResponse(result.model_dump(mode="json"))
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(
                status_code=422, detail="change control denied or invalid"
            ) from error

    @api.post("/v1/modules/M27-07/verify")
    async def verify(request: Request) -> JSONResponse:
        try:
            value = await _body(request)
            result = ComplexActivityChangeControlResult.model_validate(value, strict=True)
            return JSONResponse({"verified": service.verify(result)})
        except HTTPException:
            raise
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="result verification failed") from error

    return api


app = create_app()

__all__ = ["app", "create_app"]

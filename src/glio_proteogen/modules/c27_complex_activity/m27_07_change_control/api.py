"""FastAPI schema, validation, execution, and verification routes."""

# ruff: noqa: C901, TRY003, TRY004, TRY300, TRY301

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from glio_proteogen.contracts.m27_07 import (
    M2707_MAX_CANONICAL_REQUEST_BYTES,
    M2707_MAX_CANONICAL_RESULT_BYTES,
    ComplexActivityChangeControlResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c27_complex_activity.m27_07_change_control.service import M2707Service


async def _read_body(request: Request, *, max_bytes: int) -> bytes:
    """Read an HTTP body without buffering beyond its contract ceiling."""

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=422, detail="request exceeds byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


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

    async def _body(request: Request, *, max_bytes: int) -> dict[str, Any]:
        try:
            raw = await _read_body(request, max_bytes=max_bytes)
            value = strict_json_loads(raw, max_bytes=max_bytes)
            if not isinstance(value, dict):
                raise ValueError("object required")
            return value
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="request validation failed") from error

    @api.post("/v1/modules/M27-07/validate")
    async def validate(request: Request) -> JSONResponse:
        try:
            value = await _body(request, max_bytes=M2707_MAX_CANONICAL_REQUEST_BYTES)
            parsed = service.validate_request(value)
            return JSONResponse(parsed.model_dump(mode="json"))
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=422, detail="request validation failed") from error

    @api.post("/v1/modules/M27-07/control")
    async def control(request: Request) -> JSONResponse:
        try:
            value = await _body(request, max_bytes=M2707_MAX_CANONICAL_REQUEST_BYTES)
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
            raw = await _read_body(request, max_bytes=M2707_MAX_CANONICAL_RESULT_BYTES)
            value = strict_json_loads(raw, max_bytes=M2707_MAX_CANONICAL_RESULT_BYTES)
            if not isinstance(value, dict):
                raise ValueError("object required")
            result = ComplexActivityChangeControlResult.model_validate_json(
                canonical_json_bytes(value), strict=True
            )
            return JSONResponse({"verified": service.verify(result)})
        except HTTPException:
            raise
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="result verification failed") from error

    return api


app = create_app()

__all__ = ["app", "create_app"]

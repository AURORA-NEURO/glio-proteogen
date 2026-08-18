"""Small FastAPI boundary for the provisional M09-07 operation."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from glio_proteogen.contracts.m09_07 import (
    M0907_CONTRACT_VERSION,
    M0907_MAX_CANONICAL_REQUEST_BYTES,
    M0907_MAX_CANONICAL_RESULT_BYTES,
    contract_json_schemas,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)

from .engine import M0907AuthorizationError
from .service import M0907Service


def _error(status: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": error_type, "message": message}},
    )


def create_app(service: M0907Service | None = None) -> FastAPI:
    """Create an isolated app whose request body is parsed exactly once."""

    application = FastAPI(
        title="GLIO-PROTEOGEN M09-07 calibration/selective prediction",
        version=M0907_CONTRACT_VERSION,
    )
    active_service = service or M0907Service()

    @application.get("/m09-07/schema")
    async def schema() -> dict[str, Any]:
        return {"module": "GLIO-PROTEOGEN-M09-07", "schemas": contract_json_schemas()}

    @application.post("/m09-07/calibrate")
    async def calibrate(request: Request) -> JSONResponse:
        try:
            raw = await request.body()
            decoded = strict_json_loads(raw, max_bytes=M0907_MAX_CANONICAL_REQUEST_BYTES)
        except StrictJsonError as error:
            return JSONResponse(
                status_code=400,
                content={"error": strict_json_error_detail(error)},
            )
        try:
            typed = active_service.validate_request(decoded)
        except ValidationError as error:
            return JSONResponse(
                status_code=422,
                content={"errors": sanitized_validation_errors(error)},
            )
        except M0907AuthorizationError:
            return _error(403, "authorization_failed", "required controls were not accepted")
        try:
            result = active_service.execute(typed)
        except (ValidationError, ValueError):
            return _error(422, "contract_rejected", "request does not satisfy the module contract")
        return JSONResponse(content=result.model_dump(mode="json"))

    @application.post("/m09-07/verify")
    async def verify(request: Request) -> JSONResponse:
        try:
            decoded = strict_json_loads(
                await request.body(), max_bytes=M0907_MAX_CANONICAL_RESULT_BYTES
            )
            if not isinstance(decoded, dict):
                return _error(400, "invalid_document", "verification input must be an object")
            result = decoded.get("result")
            original = decoded.get("request")
            valid = active_service.verify(result, original)
        except StrictJsonError as error:
            return JSONResponse(status_code=400, content={"error": strict_json_error_detail(error)})
        return JSONResponse(content={"valid": valid})

    return application


app = create_app()

__all__ = ["app", "create_app"]

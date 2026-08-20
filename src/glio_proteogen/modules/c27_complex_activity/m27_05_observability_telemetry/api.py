"""FastAPI boundary for strict M27-05 telemetry emission."""

from __future__ import annotations

from typing import cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m27_05 import (
    M2705_MAX_CANONICAL_REQUEST_BYTES,
    M2705_MAX_CANONICAL_RESULT_BYTES,
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2705AuthorizationError
from .service import M2705Service

_REQUEST_ADAPTER = TypeAdapter(EmitProteomicsTelemetryRequest)
_RESULT_ADAPTER = TypeAdapter(ProteomicsTelemetryResult)
_CONTRACT_NAMES = frozenset(
    {
        "request",
        "output",
        "stream",
        "sample",
        "dashboard",
        "alert",
        "reviewer-action",
        "safe-failure",
    }
)


def _invalid_request(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M27-05 contract")


def _parse_request(body: bytes) -> EmitProteomicsTelemetryRequest:
    try:
        strict_json_loads(body, max_bytes=M2705_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _invalid_request(error) from error


def create_app(service: M2705Service | None = None) -> FastAPI:
    """Create schema, validation, emission, and replay routes."""

    boundary = service or M2705Service()
    app = FastAPI(title="GLIO-PROTEOGEN M27-05", version="0.1.0-provisional")

    @app.get("/v1/modules/M27-05/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M27-05/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M27-05 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M27-05/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M2705AuthorizationError) as error:
            raise _invalid_request(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M27-05/emit")
    async def emit(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            result = boundary.emit(payload)
        except (ValidationError, ValueError, M2705AuthorizationError) as error:
            raise _invalid_request(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M27-05/verify")
    async def verify(request: Request) -> dict[str, object]:
        try:
            candidate = strict_json_loads(
                await request.body(), max_bytes=M2705_MAX_CANONICAL_RESULT_BYTES
            )
            result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
            replay = boundary.replay(result)
        except (StrictJsonError, ValueError, ValidationError, TypeError) as error:
            raise HTTPException(status_code=422, detail="replay envelope is invalid") from error
        return {
            "verified": replay.result_digest == result.result_digest,
            "result_digest": replay.result_digest,
        }

    return app


__all__ = ["create_app"]

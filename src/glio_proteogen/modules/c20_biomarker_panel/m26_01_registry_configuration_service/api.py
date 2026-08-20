"""FastAPI boundary for strict M26-01 registry resolution."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_01 import (
    M2601_MAX_CANONICAL_REQUEST_BYTES,
    M2601_MAX_CANONICAL_RESULT_BYTES,
    ProteinSubtypeRegistryResult,
    RegisterProteinSubtypeRegistryRequest,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2601AuthorizationError
from .service import M2601Service

_REQUEST_ADAPTER = TypeAdapter(RegisterProteinSubtypeRegistryRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypeRegistryResult)
_CONTRACT_NAMES = frozenset(
    {"request", "output", "entry", "history", "binding", "configuration", "registry", "finding"}
)


def _invalid_request(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M26-01 contract")


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


def _parse_request(body: bytes) -> RegisterProteinSubtypeRegistryRequest:
    try:
        strict_json_loads(body, max_bytes=M2601_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _invalid_request(error) from error


def _parse_object(
    body: bytes,
    *,
    max_bytes: int = M2601_MAX_CANONICAL_REQUEST_BYTES,
    invalid_detail: str = "request JSON is invalid",
    object_detail: str = "request JSON must be an object",
) -> dict[str, Any]:
    try:
        value = strict_json_loads(body, max_bytes=max_bytes)
    except (StrictJsonError, ValueError) as error:
        raise HTTPException(status_code=422, detail=invalid_detail) from error
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail=object_detail)
    return cast("dict[str, Any]", value)


def create_app(service: M2601Service | None = None) -> FastAPI:
    """Create strict schema, validation, registration, and replay routes."""

    boundary = service or M2601Service()
    app = FastAPI(title="GLIO-PROTEOGEN M26-01", version="0.1.0-provisional")

    @app.get("/v1/modules/M26-01/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M26-01/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M26-01 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M26-01/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(
            await _read_body(request, max_bytes=M2601_MAX_CANONICAL_REQUEST_BYTES)
        )
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M2601AuthorizationError) as error:
            raise _invalid_request(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M26-01/register")
    async def register(request: Request) -> dict[str, object]:
        payload = _parse_request(
            await _read_body(request, max_bytes=M2601_MAX_CANONICAL_REQUEST_BYTES)
        )
        try:
            result = boundary.register(payload)
        except (ValidationError, ValueError, M2601AuthorizationError) as error:
            raise _invalid_request(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M26-01/verify")
    async def verify(request: Request) -> dict[str, object]:
        envelope = _parse_object(
            await _read_body(request, max_bytes=M2601_MAX_CANONICAL_RESULT_BYTES),
            max_bytes=M2601_MAX_CANONICAL_RESULT_BYTES,
            invalid_detail="replay envelope JSON is invalid",
            object_detail="replay envelope JSON must be an object",
        )
        candidate = envelope.get("result", envelope)
        try:
            result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
            replay = boundary.replay(result)
        except (ValidationError, ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="replay envelope is invalid") from error
        return {
            "verified": replay.result_digest == result.result_digest,
            "result_digest": replay.result_digest,
        }

    return app


__all__ = ["create_app"]

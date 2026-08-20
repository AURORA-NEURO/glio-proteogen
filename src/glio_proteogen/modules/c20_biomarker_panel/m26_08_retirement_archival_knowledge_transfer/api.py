"""FastAPI boundary for strict M26-08 retirement operations."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_08 import (
    M2608_MAX_CANONICAL_REQUEST_BYTES,
    M2608_MAX_CANONICAL_RESULT_BYTES,
    ContractName,
    ProteinSubtypeRetirementResult,
    RetireProteinSubtypeServiceRequest,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2608AuthorizationError
from .service import M2608RetirementService

_REQUEST_ADAPTER = TypeAdapter(RetireProteinSubtypeServiceRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypeRetirementResult)
_CONTRACT_NAMES = frozenset(
    {
        "request",
        "output",
        "criterion",
        "migration",
        "evidence",
        "communication",
        "archive",
        "configuration",
        "package",
        "finding",
    }
)


def _invalid_request(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M26-08 contract")


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


def _parse_request(body: bytes) -> RetireProteinSubtypeServiceRequest:
    try:
        strict_json_loads(body, max_bytes=M2608_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _invalid_request(error) from error


def _parse_object(body: bytes) -> dict[str, Any]:
    try:
        value = strict_json_loads(body, max_bytes=M2608_MAX_CANONICAL_RESULT_BYTES)
    except (StrictJsonError, ValueError) as error:
        raise HTTPException(status_code=422, detail="request JSON is invalid") from error
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="request JSON must be an object")
    return cast("dict[str, Any]", value)


def create_app(service: M2608RetirementService | None = None) -> FastAPI:
    """Create strict schema, validation, retirement, and replay routes."""

    boundary = service or M2608RetirementService()
    app = FastAPI(title="GLIO-PROTEOGEN M26-08", version="0.1.0-provisional")

    @app.get("/v1/modules/M26-08/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M26-08/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M26-08 contract")
        return contract_json_schema(cast("ContractName", name))

    @app.post("/v1/modules/M26-08/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(
            await _read_body(request, max_bytes=M2608_MAX_CANONICAL_REQUEST_BYTES)
        )
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M2608AuthorizationError) as error:
            raise _invalid_request(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M26-08/retire")
    async def retire(request: Request) -> dict[str, object]:
        payload = _parse_request(
            await _read_body(request, max_bytes=M2608_MAX_CANONICAL_REQUEST_BYTES)
        )
        try:
            result = boundary.retire(payload)
        except (ValidationError, ValueError, M2608AuthorizationError) as error:
            raise _invalid_request(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M26-08/verify")
    async def verify(request: Request) -> dict[str, object]:
        envelope = _parse_object(
            await _read_body(request, max_bytes=M2608_MAX_CANONICAL_RESULT_BYTES)
        )
        candidate = envelope.get("result", envelope)
        try:
            result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
            replay = boundary.verify(result)
        except (ValidationError, ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="replay envelope is invalid") from error
        return {"verified": True, "result_digest": replay.result_digest}

    return app


app = create_app()

__all__ = ["app", "create_app"]

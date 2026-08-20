"""FastAPI boundary for strict M27-06 security/access evaluation."""

from __future__ import annotations

from typing import cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m27_06 import (
    M2706_MAX_CANONICAL_REQUEST_BYTES,
    M2706_MAX_CANONICAL_RESULT_BYTES,
    ComplexActivitySecurityAccessResult,
    EvaluateComplexActivitySecurityAccessRequest,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2706AuthorizationError
from .service import M2706Service

_REQUEST_ADAPTER = TypeAdapter(EvaluateComplexActivitySecurityAccessRequest)
_RESULT_ADAPTER = TypeAdapter(ComplexActivitySecurityAccessResult)
_CONTRACT_NAMES = frozenset(
    {
        "request",
        "output",
        "access-decision",
        "audit-event",
        "posture",
        "control",
        "finding",
        "safe-failure",
    }
)


def _invalid(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M27-06 contract")


def _parse_request(body: bytes) -> EvaluateComplexActivitySecurityAccessRequest:
    try:
        strict_json_loads(body, max_bytes=M2706_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _invalid(error) from error


async def _read_bounded(request: Request, *, max_bytes: int) -> bytes:
    """Drain an HTTP body while retaining at most the contract byte ceiling."""

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=422, detail="request exceeds byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def create_app(service: M2706Service | None = None) -> FastAPI:
    """Create schema, validation, evaluation, and replay routes."""

    boundary = service or M2706Service()
    app = FastAPI(title="GLIO-PROTEOGEN M27-06", version="0.1.0-provisional")

    @app.get("/v1/modules/M27-06/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M27-06/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M27-06 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M27-06/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(
            await _read_bounded(request, max_bytes=M2706_MAX_CANONICAL_REQUEST_BYTES)
        )
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M2706AuthorizationError) as error:
            raise _invalid(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M27-06/evaluate")
    async def evaluate(request: Request) -> dict[str, object]:
        payload = _parse_request(
            await _read_bounded(request, max_bytes=M2706_MAX_CANONICAL_REQUEST_BYTES)
        )
        try:
            result = boundary.emit(payload)
        except (ValidationError, ValueError, M2706AuthorizationError) as error:
            raise _invalid(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M27-06/verify")
    async def verify(request: Request) -> dict[str, object]:
        try:
            body = await _read_bounded(request, max_bytes=M2706_MAX_CANONICAL_RESULT_BYTES)
            candidate = strict_json_loads(body, max_bytes=M2706_MAX_CANONICAL_RESULT_BYTES)
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

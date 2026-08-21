"""FastAPI adapter for the provisional M22-08 evidence gate."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestSizeLimitMiddleware
from glio_proteogen.contracts.m22_08 import (
    M2208_MAX_CANONICAL_REQUEST_BYTES,
    AdjudicateProteinRnaDiscordanceEvidenceGateRequest,
    ProteinRnaDiscordanceEvidenceGateResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2208AuthorizationError
from .service import M2208Service

_REQUEST_ADAPTER = TypeAdapter(AdjudicateProteinRnaDiscordanceEvidenceGateRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinRnaDiscordanceEvidenceGateResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "requirement",
    "benchmark",
    "risk",
    "approval",
    "release-record",
    "configuration",
    "obligation",
    "finding",
}


def _safe_validation(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M22-08 contract")


def _parse_request(body: bytes) -> AdjudicateProteinRnaDiscordanceEvidenceGateRequest:
    try:
        strict_json_loads(body, max_bytes=M2208_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _safe_validation(error) from error


def _parse_object(body: bytes) -> dict[str, Any]:
    try:
        value = strict_json_loads(body, max_bytes=M2208_MAX_CANONICAL_REQUEST_BYTES)
    except (StrictJsonError, ValueError) as error:
        raise HTTPException(status_code=422, detail="request JSON is invalid") from error
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="request JSON must be an object")
    return cast("dict[str, Any]", value)


async def _read_bounded(request: Request, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=422, detail="request exceeds byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def create_app(service: M2208Service | None = None) -> FastAPI:
    """Create strict validate/adjudicate/replay API routes."""

    boundary = service or M2208Service()
    app = FastAPI(title="GLIO-PROTEOGEN M22-08", version="0.1.0-provisional")
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=M2208_MAX_CANONICAL_REQUEST_BYTES)

    @app.get("/v1/modules/M22-08/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M22-08/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M22-08 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M22-08/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(
            await _read_bounded(request, max_bytes=M2208_MAX_CANONICAL_REQUEST_BYTES)
        )
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M2208AuthorizationError) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M22-08/adjudicate")
    async def adjudicate(request: Request) -> dict[str, object]:
        payload = _parse_request(
            await _read_bounded(request, max_bytes=M2208_MAX_CANONICAL_REQUEST_BYTES)
        )
        try:
            result = boundary.adjudicate(payload)
        except (ValidationError, ValueError, M2208AuthorizationError) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M22-08/verify")
    async def verify(request: Request) -> dict[str, object]:
        envelope = _parse_object(
            await _read_bounded(request, max_bytes=M2208_MAX_CANONICAL_REQUEST_BYTES)
        )
        candidate = envelope.get("result", envelope)
        supplied_request = envelope.get("request")
        try:
            result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
            typed_request = (
                _REQUEST_ADAPTER.validate_json(
                    canonical_json_bytes(supplied_request), strict=True
                )
                if supplied_request is not None
                else None
            )
            replay = boundary.replay(result, typed_request)
        except (ValidationError, ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="replay envelope is invalid") from error
        return {
            "verified": replay.result_digest == result.result_digest,
            "result_digest": replay.result_digest,
        }

    return app


__all__ = ["create_app"]

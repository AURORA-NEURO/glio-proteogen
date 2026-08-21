"""FastAPI adapter for provisional M24-07 operational evaluation."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestSizeLimitMiddleware
from glio_proteogen.contracts.m24_07 import (
    M2407_MAX_CANONICAL_REQUEST_BYTES,
    M2407_MAX_CANONICAL_RESULT_BYTES,
    BiomarkerPanelHumanFactorsResult,
    EvaluateBiomarkerPanelHumanFactorsRequest,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2407AuthorizationError
from .service import M2407Service

_REQUEST_ADAPTER = TypeAdapter(EvaluateBiomarkerPanelHumanFactorsRequest)
_RESULT_ADAPTER = TypeAdapter(BiomarkerPanelHumanFactorsResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "report",
    "metric",
    "fallback",
    "configuration",
    "finding",
}


def _safe_validation(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M24-07 contract")


def _parse_request(body: bytes) -> EvaluateBiomarkerPanelHumanFactorsRequest:
    try:
        strict_json_loads(body, max_bytes=M2407_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _safe_validation(error) from error


def _parse_object(
    body: bytes,
    *,
    max_bytes: int = M2407_MAX_CANONICAL_REQUEST_BYTES,
) -> dict[str, Any]:
    try:
        value = strict_json_loads(body, max_bytes=max_bytes)
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


def create_app(service: M2407Service | None = None) -> FastAPI:
    """Create strict validation/evaluation/replay routes."""

    boundary = service or M2407Service()
    app = FastAPI(title="GLIO-PROTEOGEN M24-07", version="0.1.0-provisional")
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=M2407_MAX_CANONICAL_REQUEST_BYTES,
        result_max_bytes=M2407_MAX_CANONICAL_RESULT_BYTES,
    )

    @app.get("/v1/modules/M24-07/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M24-07/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M24-07 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M24-07/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(
            await _read_bounded(request, max_bytes=M2407_MAX_CANONICAL_REQUEST_BYTES)
        )
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M2407AuthorizationError) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M24-07/evaluate")
    async def evaluate(request: Request) -> dict[str, object]:
        payload = _parse_request(
            await _read_bounded(request, max_bytes=M2407_MAX_CANONICAL_REQUEST_BYTES)
        )
        try:
            result = boundary.evaluate(payload)
        except (ValidationError, ValueError, M2407AuthorizationError) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M24-07/verify")
    async def verify(request: Request) -> dict[str, object]:
        envelope = _parse_object(
            await _read_bounded(request, max_bytes=M2407_MAX_CANONICAL_RESULT_BYTES),
            max_bytes=M2407_MAX_CANONICAL_RESULT_BYTES,
        )
        candidate = envelope.get("result", envelope)
        supplied_request = envelope.get("request")
        try:
            result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
            typed_request = (
                _REQUEST_ADAPTER.validate_json(canonical_json_bytes(supplied_request), strict=True)
                if supplied_request is not None
                else None
            )
            replay = boundary.verify_replay(result, typed_request)
        except (ValidationError, ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="replay envelope is invalid") from error
        return {
            "verified": replay.result_digest == result.result_digest,
            "result_digest": replay.result_digest,
        }

    return app


__all__ = ["create_app"]

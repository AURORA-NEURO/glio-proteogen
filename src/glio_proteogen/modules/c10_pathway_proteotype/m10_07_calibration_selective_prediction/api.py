"""FastAPI adapter for the provisional M10-07 service boundary."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m10_07 import (
    M1007_MAX_CANONICAL_REQUEST_BYTES,
    CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M1007AuthorizationError, M1007InputError
from .service import M1007Service

_REQUEST_ADAPTER = TypeAdapter(CalibrateProteinRnaDiscordanceSelectivePredictionRequest)


def _parse_body(body: bytes) -> dict[str, Any]:
    try:
        payload = strict_json_loads(body)
    except (StrictJsonError, ValueError) as error:
        raise HTTPException(status_code=422, detail="request JSON is invalid") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="request JSON must be an object")
    return payload


def _safe_validation(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M10-07 contract")


def _parse_request(body: bytes) -> CalibrateProteinRnaDiscordanceSelectivePredictionRequest:
    try:
        strict_json_loads(body, max_bytes=M1007_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _safe_validation(error) from error


def create_app(service: M1007Service | None = None) -> FastAPI:
    """Create an API app with strict validation and sanitized errors."""

    boundary = service or M1007Service()
    app = FastAPI(title="GLIO-PROTEOGEN M10-07", version="0.1.0-provisional")

    @app.get("/v1/modules/M10-07/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M10-07/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in {
            "request",
            "output",
            "configuration",
            "scope",
            "estimate",
            "prediction-set",
            "diagnostic",
        }:
            raise HTTPException(status_code=404, detail="unknown M10-07 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M10-07/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M1007AuthorizationError) as error:
            raise _safe_validation(error) from error
        return typed.model_dump(mode="json")

    @app.post("/v1/modules/M10-07/execute")
    async def execute(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            built = boundary.execute(payload)
        except (ValidationError, ValueError, M1007AuthorizationError, M1007InputError) as error:
            raise _safe_validation(error) from error
        return {
            "result": built.result.model_dump(mode="json"),
            "canonical": built.canonical_bytes.decode("utf-8"),
        }

    @app.post("/v1/modules/M10-07/verify")
    async def verify(request: Request) -> dict[str, object]:
        envelope = _parse_body(await request.body())
        result = envelope.get("result")
        canonical = envelope.get("canonical")
        if not isinstance(result, dict) or not isinstance(canonical, (str, dict)):
            raise HTTPException(status_code=422, detail="verify envelope is invalid")
        canonical_bytes = (
            canonical_json_bytes(canonical)
            if isinstance(canonical, dict)
            else canonical.encode("utf-8")
        )
        replay = boundary.verify(result, canonical_bytes)
        return {
            "verified": replay.verified,
            "reason": replay.reason,
            "result_digest": replay.result_digest,
        }

    return app


__all__ = ["create_app"]

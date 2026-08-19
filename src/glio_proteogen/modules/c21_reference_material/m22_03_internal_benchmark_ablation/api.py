"""FastAPI adapter for the provisional M22-03 benchmark boundary."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m22_03 import (
    M2203_MAX_CANONICAL_REQUEST_BYTES,
    M2203_MAX_CANONICAL_RESULT_BYTES,
    ProteinRnaDiscordanceInternalBenchmarkResult,
    RunProteinRnaDiscordanceInternalBenchmarkRequest,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2203AuthorizationError
from .service import M2203Service

_REQUEST_ADAPTER = TypeAdapter(RunProteinRnaDiscordanceInternalBenchmarkRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinRnaDiscordanceInternalBenchmarkResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "dossier",
    "split",
    "baseline",
    "metric",
    "ablation",
    "comparison",
    "finding",
}


def _safe_validation(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M22-03 contract")


def _parse_request(body: bytes) -> RunProteinRnaDiscordanceInternalBenchmarkRequest:
    try:
        strict_json_loads(body, max_bytes=M2203_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _safe_validation(error) from error


def _parse_object(body: bytes) -> dict[str, Any]:
    try:
        value = strict_json_loads(body, max_bytes=M2203_MAX_CANONICAL_RESULT_BYTES)
    except (StrictJsonError, ValueError) as error:
        raise HTTPException(status_code=422, detail="request JSON is invalid") from error
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="request JSON must be an object")
    return cast("dict[str, Any]", value)


def create_app(service: M2203Service | None = None) -> FastAPI:
    """Create strict validate/run/replay API routes with sanitized errors."""

    boundary = service or M2203Service()
    app = FastAPI(title="GLIO-PROTEOGEN M22-03", version="0.1.0-provisional")

    @app.get("/v1/modules/M22-03/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M22-03/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M22-03 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M22-03/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M2203AuthorizationError) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M22-03/benchmark")
    async def benchmark(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            result = boundary.generate(payload)
        except (ValidationError, ValueError, M2203AuthorizationError) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M22-03/verify")
    async def verify(request: Request) -> dict[str, object]:
        envelope = _parse_object(await request.body())
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
